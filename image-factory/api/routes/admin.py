from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from starlette.responses import StreamingResponse
from sqlalchemy import desc

from api.dependencies import get_redis
from database.session import get_session
from database.models.job import Job
from database.models.notification import Notification
from configs.logging import get_logger
from configs.settings import settings
from services.settings_service import get_provider_api_key, set_provider_api_key, get_provider_keys_status, get_setting, set_setting, get_claude_config, set_claude_config, get_pricing_config, set_pricing_config, get_img2img_config, set_img2img_config, get_storage_config, set_storage_config, get_all_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/status")
async def admin_status():
    return {"status": "ok"}


@router.get("/notifications")
async def list_notifications(
    limit: int = 50,
    severity: str | None = None,
    redis: aioredis.Redis = Depends(get_redis),
):
    raw = await redis.lrange("admin:notifications", 0, limit - 1)
    notifications = [json.loads(n) for n in raw]
    if severity:
        notifications = [n for n in notifications if n["severity"] == severity]
    return {"notifications": notifications, "total": len(notifications)}


@router.delete("/notifications")
async def clear_notifications(redis: aioredis.Redis = Depends(get_redis)):
    await redis.delete("admin:notifications")
    return {"status": "cleared"}


@router.get("/notifications/db")
async def list_db_notifications(
    limit: int = 50,
    offset: int = 0,
    level: str | None = None,
    user_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Notification).order_by(desc(Notification.created_at))
    if level:
        query = query.where(Notification.level == level)
    if user_id:
        query = query.where(Notification.user_id == user_id)
    result = await session.execute(query.offset(offset).limit(limit))
    notifications = list(result.scalars().all())
    return {
        "notifications": [
            {
                "id": n.id,
                "user_id": n.user_id,
                "type": n.type,
                "level": n.level,
                "title": n.title,
                "message": n.message,
                "project_id": n.project_id,
                "run_id": n.run_id,
                "data": n.data,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": len(notifications),
    }


@router.patch("/notifications/db/{notification_id}/read")
async def mark_notification_read_db(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.read = True
        await session.commit()
        return {"status": "read"}
    return {"status": "not_found"}


@router.get("/queue/status", summary="Queue state overview")
async def queue_status(
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    paused = await redis.get("queue:paused")
    high_priority = await session.execute(
        select(func.count(Job.id)).where(
            and_(Job.status == "queued", Job.is_bulk_item == True)
        )
    )
    normal_queue = await session.execute(
        select(func.count(Job.id)).where(
            and_(Job.status == "queued", Job.is_bulk_item == True)
        )
    )
    active = await session.execute(
        select(func.count(Job.id)).where(Job.status == "processing")
    )
    dead_letter = await session.execute(
        select(func.count(Job.id)).where(and_(Job.status == "failed", Job.retry_count >= Job.max_retries))
    )

    hp = high_priority.scalar() or 0
    nq = normal_queue.scalar() or 0
    return {
        "paused": paused is not None and paused == b"1",
        "high_priority_depth": min(hp, 5),  # approximate — meta priority JSONB filtering deferred
        "normal_priority_depth": nq,
        "active_workers": active.scalar() or 0,
        "dead_letter_count": dead_letter.scalar() or 0,
    }


@router.post("/queue/pause", summary="Pause queue")
async def pause_queue(redis: aioredis.Redis = Depends(get_redis)):
    await redis.set("queue:paused", "1", ex=86400)
    logger.info("queue_paused")
    return {"status": "paused"}


@router.post("/queue/resume", summary="Resume queue")
async def resume_queue(redis: aioredis.Redis = Depends(get_redis)):
    await redis.delete("queue:paused")
    logger.info("queue_resumed")
    return {"status": "resumed"}


@router.post("/jobs/retry-all-failed", summary="Requeue all failed jobs from last 24h")
async def retry_all_failed(
    session: AsyncSession = Depends(get_session),
):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await session.execute(
        select(Job).where(
            and_(Job.status == "failed", Job.updated_at >= cutoff)
        )
    )
    failed_jobs = list(result.scalars().all())

    from workers.celery_app import celery_app

    retried = 0
    for job in failed_jobs:
        j_meta = job.meta or {}
        url = j_meta.get("url", "")
        if url:
            await session.execute(
                update(Job).where(Job.id == job.id).values(
                    status="queued",
                    error_message="",
                    retry_count=0,
                    progress=0.0,
                    updated_at=datetime.utcnow(),
                )
            )
            celery_app.send_task("tasks.product.process_single_product", args=[job.id, url, job.project_name])
            retried += 1

    await session.commit()
    logger.info("retry_all_failed", count=retried)
    return {"status": "retrying", "retried_count": retried}


@router.delete("/jobs/clear-completed", summary="Archive and remove completed jobs older than 7 days")
async def clear_completed(
    session: AsyncSession = Depends(get_session),
):
    cutoff = datetime.utcnow() - timedelta(days=7)
    result = await session.execute(
        select(Job).where(
            and_(Job.status == "completed", Job.completed_at < cutoff)
        )
    )
    old_jobs = list(result.scalars().all())

    if not old_jobs:
        return {"status": "no_jobs_to_clear", "count": 0}

    archive_rows = []
    for j in old_jobs:
        j_meta = j.meta or {}
        archive_rows.append({
            "id": j.id,
            "type": j.type,
            "status": j.status,
            "project_name": j.project_name,
            "url": j_meta.get("url", ""),
            "product_name": j_meta.get("product_name", ""),
            "drive_folder_url": j_meta.get("drive_folder_url", ""),
            "error_message": j.error_message or "",
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "completed_at": j.completed_at.isoformat() if j.completed_at else "",
            "archived_at": datetime.utcnow().isoformat(),
        })

    from pathlib import Path
    from configs.settings import settings
    archive_dir = Path(settings.storage_path) / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"jobs_archive_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    archive_path.write_text(json.dumps(archive_rows, indent=2))

    for j in old_jobs:
        await session.execute(delete(Job).where(Job.id == j.id))

    await session.commit()
    logger.info("clear_completed", count=len(old_jobs), archive=str(archive_path))
    return {"status": "cleared", "count": len(old_jobs), "archive_path": str(archive_path)}


@router.get("/export/jobs.csv", summary="Export job history as CSV")
async def export_jobs_csv(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Job).order_by(Job.created_at.desc()).limit(10000)
    )
    jobs = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Type", "Status", "Product Name", "URL", "Created At", "Completed At", "Duration (s)", "Drive URL", "Error"])

    for j in jobs:
        j_meta = j.meta or {}
        duration = ""
        if j.completed_at and j.created_at:
            duration = str(int((j.completed_at - j.created_at).total_seconds()))
        writer.writerow([
            j.id,
            j.type,
            j.status,
            j_meta.get("product_name", ""),
            j_meta.get("url", ""),
            j.created_at.isoformat() if j.created_at else "",
            j.completed_at.isoformat() if j.completed_at else "",
            duration,
            j_meta.get("drive_folder_url", ""),
            j.error_message or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs_export.csv"},
    )


@router.get("/provider-keys", summary="Get masked status of all provider API keys")
async def list_provider_keys(session: AsyncSession = Depends(get_session)):
    return await get_provider_keys_status(session)


@router.put("/provider-keys/nano-banana", summary="Update Nano Banana API key (persisted to DB)")
async def update_nano_banana_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    await set_provider_api_key("nano_banana_api_key", key.strip(), session)
    from services.nano_banana.credit_balancer import get_credit_balancer
    get_credit_balancer().invalidate_cache()
    return {"status": "updated", "key": key[:8] + "..." + key[-4:] if len(key) > 12 else "***"}


@router.put("/provider-keys/gemini", summary="Update Gemini API key (persisted to DB)")
async def update_gemini_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    await set_provider_api_key("gemini_api_key", key.strip(), session)
    from services.nano_banana.credit_balancer import get_credit_balancer
    get_credit_balancer().invalidate_cache()
    return {"status": "updated", "key": key[:8] + "..." + key[-4:] if len(key) > 12 else "***"}


@router.get("/budget", summary="Get current monthly budget in cents")
async def get_budget(session: AsyncSession = Depends(get_session)):
    db_val = await get_setting("monthly_budget_cents", session, "")
    budget = int(db_val) if db_val else settings.monthly_budget_cents
    return {
        "monthly_budget_cents": budget,
        "monthly_budget_dollars": round(budget / 100, 2),
        "source": "database" if db_val else "env_file",
    }


@router.put("/budget", summary="Update monthly budget (persisted to DB)")
async def update_budget(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    cents = body.get("monthly_budget_cents")
    if cents is None or not isinstance(cents, int) or cents < 0:
        raise HTTPException(status_code=400, detail="monthly_budget_cents must be a non-negative integer")
    await set_setting("monthly_budget_cents", str(cents), session)
    from services.nano_banana.credit_balancer import get_credit_balancer
    get_credit_balancer().invalidate_cache()
    return {
        "status": "updated",
        "monthly_budget_cents": cents,
        "monthly_budget_dollars": round(cents / 100, 2),
    }


@router.get("/settings", summary="Get all configurable settings grouped by category")
async def list_all_settings(session: AsyncSession = Depends(get_session)):
    return await get_all_settings(session)


@router.put("/provider-keys/claude", summary="Update Claude API key (persisted to DB)")
async def update_claude_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    await set_provider_api_key("claude_api_key", key.strip(), session)
    return {"status": "updated", "key": key[:8] + "..." + key[-4:] if len(key) > 12 else "***"}


@router.get("/settings/claude", summary="Get Claude model configuration")
async def get_claude_settings(session: AsyncSession = Depends(get_session)):
    return await get_claude_config(session)


@router.put("/settings/claude", summary="Update Claude model configuration")
async def update_claude_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    model = body.get("claude_model", "claude-sonnet-4-20250514")
    max_tokens = body.get("claude_max_tokens", 4096)
    temperature = body.get("claude_temperature", 0.7)
    if not isinstance(max_tokens, int) or max_tokens < 1:
        raise HTTPException(status_code=400, detail="claude_max_tokens must be a positive integer")
    if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 1:
        raise HTTPException(status_code=400, detail="claude_temperature must be between 0 and 1")
    await set_claude_config(model, max_tokens, temperature, session)
    return {"status": "updated", "claude_model": model, "claude_max_tokens": max_tokens, "claude_temperature": temperature}


@router.get("/settings/pricing", summary="Get pricing configuration")
async def get_pricing_settings(session: AsyncSession = Depends(get_session)):
    return await get_pricing_config(session)


@router.put("/settings/pricing", summary="Update pricing configuration")
async def update_pricing_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    cost_per_image = body.get("cost_per_image_cents", 1.0)
    cost_per_claude = body.get("cost_per_claude_call_cents", 0.03)
    if not isinstance(cost_per_image, (int, float)) or cost_per_image < 0:
        raise HTTPException(status_code=400, detail="cost_per_image_cents must be a non-negative number")
    if not isinstance(cost_per_claude, (int, float)) or cost_per_claude < 0:
        raise HTTPException(status_code=400, detail="cost_per_claude_call_cents must be a non-negative number")
    await set_pricing_config(float(cost_per_image), float(cost_per_claude), session)
    from services.nano_banana.credit_balancer import get_credit_balancer
    get_credit_balancer().invalidate_cache()
    return {"status": "updated", "cost_per_image_cents": cost_per_image, "cost_per_claude_call_cents": cost_per_claude}


@router.get("/settings/img2img", summary="Get image-to-image model configuration")
async def get_img2img_settings(session: AsyncSession = Depends(get_session)):
    return await get_img2img_config(session)


@router.put("/settings/img2img", summary="Update image-to-image model")
async def update_img2img_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    model = body.get("img2img_model", "google/imagen-4")
    try:
        await set_img2img_config(model, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "updated", "img2img_model": model}


@router.get("/settings/storage", summary="Get storage/output directory configuration")
async def get_storage_settings(session: AsyncSession = Depends(get_session)):
    return await get_storage_config(session)


@router.put("/settings/storage", summary="Update storage/output directory path")
async def update_storage_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    path = body.get("storage_local_path", "")
    if not path:
        raise HTTPException(status_code=400, detail="storage_local_path is required")
    await set_storage_config(path.strip(), session)
    return {"status": "updated", "storage_local_path": path.strip()}


@router.get("/scrapfly/usage", summary="Get Scrapfly credit usage")
async def get_scrapfly_usage(
    redis: aioredis.Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
):
    usage = await redis.hgetall("scrapfly:usage")
    remaining_project_key = await redis.get("scrapfly:remaining_project")
    parsed = {}
    total_cost = 0
    total_requests = 0
    for k, v in usage.items():
        k = k.decode() if isinstance(k, bytes) else k
        v = int(v.decode()) if isinstance(v, bytes) else int(v)
        parsed[k] = v
        if k == "total_cost":
            total_cost = v
        elif k.endswith(":cost"):
            total_requests += 1

    # ScrapFly 'x-scrapfly-remaining-api-credit' is ACCOUNT-level, not per-key.
    # All keys share the same account pool. We take the max tracked value as
    # our best knowledge of account-level remaining.
    account_remaining = 0
    for k, v in parsed.items():
        if k.endswith(":remaining"):
            account_remaining = max(account_remaining, v)
    # If no request has been made yet, we simply don't know the remaining
    has_usage_data = total_requests > 0

    remaining_project_val = int(remaining_project_key.decode()) if remaining_project_key else 0

    monthly_budget = settings.scrapfly_monthly_budget

    from services.scrapfly_key_manager import get_keys_with_usage
    keys = await get_keys_with_usage(session, redis)

    # Primary: account-level remaining (from response headers). Fallback: project-level.
    remaining = account_remaining or remaining_project_val or 0

    avg_cost_per_request = round(total_cost / total_requests, 1) if total_requests > 0 else 9
    # ScrapFly billing: 9 pts base for CAPTCHA-bypass (asp=true)
    cost_per_product = max(avg_cost_per_request, 9)

    scrapes_remaining_budget = max(0, (monthly_budget - total_cost) // cost_per_product) if cost_per_product > 0 else 0
    scrapes_remaining_actual = max(0, remaining // cost_per_product) if cost_per_product > 0 else 0

    return {
        "total_cost": total_cost,
        "total_requests": total_requests,
        "avg_cost_per_request": avg_cost_per_request,
        "cost_per_product": cost_per_product,
        "remaining_credits": remaining,
        "has_usage_data": has_usage_data,
        "monthly_budget": monthly_budget,
        "budget_left": max(0, monthly_budget - total_cost),
        "scrapes_remaining_budget": scrapes_remaining_budget,
        "scrapes_remaining_actual": scrapes_remaining_actual,
        "per_key_summary": [
            {
                "key": k["key_preview"],
                "used": k["used"],
                "remaining": k["remaining"] if k["remaining"] > 0 else None,
                "status": "tracked" if k["remaining"] > 0 else "untracked",
            }
            for k in keys
        ],
        "products_possible": max(0, (monthly_budget - total_cost) // cost_per_product) if cost_per_product > 0 else 0,
        "per_key": {k: v for k, v in parsed.items() if k != "total_cost"},
        "keys": keys,
        "key_count": len(keys),
    }


@router.get("/scrapfly/keys", summary="List all Scrapfly API keys")
async def list_scrapfly_keys(
    redis: aioredis.Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
):
    from services.scrapfly_key_manager import get_keys_with_usage

    keys = await get_keys_with_usage(session, redis)
    return {"keys": keys, "total": len(keys)}


@router.post("/scrapfly/keys", summary="Add a Scrapfly API key")
async def add_scrapfly_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "").strip()
    if not key or not key.startswith("scp-"):
        raise HTTPException(status_code=400, detail="Invalid Scrapfly API key format")
    from services.scrapfly_key_manager import add_key

    await add_key(key, session)
    return {"status": "added", "key_preview": key[:20] + "..."}


@router.delete("/scrapfly/keys", summary="Remove a Scrapfly API key")
async def remove_scrapfly_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    from services.scrapfly_key_manager import remove_key

    await remove_key(key, session)
    return {"status": "removed", "key_preview": key[:20] + "..."}


@router.post("/products/retry-failed", summary="Retry all failed product links")
async def retry_failed_product_links(
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select, update as sql_update
    from database.models.product_link import ProductLink

    result = await session.execute(
        select(ProductLink).where(
            ProductLink.status.in_(["failed", "error"]),
        )
    )
    links = result.scalars().all()
    count = len(links)

    from workers.celery_app import celery_app

    for link in links:
        await session.execute(
            sql_update(ProductLink).where(ProductLink.id == link.id).values(
                status="pending",
                error_message=None,
                failure_type=None,
                completed_at=None,
                updated_at=datetime.utcnow(),
            )
        )
    await session.commit()

    from database.repository import JobRepository

    batch_job = JobRepository(session)
    job = await batch_job.create({
        "type": "retry_failed",
        "status": "pending",
        "meta": {"total": count, "original_count": count},
    })
    batch_id = job.id

    for link in links:
        celery_app.send_task(
            "tasks.product.process_single_product",
            args=[link.job_id, link.url, ""],
        )

    await batch_job.update(batch_id, {
        "status": "processing",
        "meta": {"total": count, "dispatched": count},
    })

    return {
        "status": "retrying",
        "total": count,
        "batch_id": batch_id,
        "message": f"Retrying {count} failed products",
    }
