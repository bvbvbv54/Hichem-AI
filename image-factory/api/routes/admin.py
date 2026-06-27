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
from database.models.product_link import ProductLink
from configs.logging import get_logger
from configs.settings import settings
from services.settings_service import get_provider_api_key, set_provider_api_key, get_provider_keys_status, get_setting, set_setting, get_claude_config, set_claude_config, get_img2img_config, set_img2img_config, get_storage_config, set_storage_config, set_storage_enabled, get_google_api_key, set_google_api_key, get_all_settings
from database.models.asset import Asset

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

    from database.models.product_link import ProductLink

    retried = 0
    for job in failed_jobs:
        j_meta = job.meta or {}
        url = j_meta.get("url", "")
        if not url:
            pl_result = await session.execute(
                select(ProductLink.url).where(ProductLink.job_id == job.id).limit(1)
            )
            row = pl_result.one_or_none()
            if row:
                url = row[0]
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
            await session.execute(
                update(ProductLink).where(ProductLink.job_id == job.id).values(
                    status="pending",
                    error_message="",
                    failure_type="",
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


@router.put("/provider-keys/google", summary="Update Google AI API key (shared for Gemini + Nano Banana, persisted to DB)")
async def update_google_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    # Basic validation: Google API keys start with "AIza"
    if not key.strip().startswith("AIza"):
        raise HTTPException(status_code=400, detail="Invalid Google API key format — must start with 'AIza'")
    await set_google_api_key(key.strip(), session)
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


# Pricing is now internal-only — configured via configs/pricing.py


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


@router.put("/settings/storage/toggle", summary="Enable or disable storage")
async def toggle_storage(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be a boolean")
    await set_storage_enabled(enabled, session)
    return {"status": "updated", "storage_enabled": enabled}


@router.get("/scrapfly/usage", summary="Get Scrapfly credit usage")
async def get_scrapfly_usage(
    session: AsyncSession = Depends(get_session),
):
    COST_PER_SCRAPE = 6
    CREDITS_PER_KEY = 1000
    import asyncio
    import httpx

    from services.scrapfly_key_manager import get_all_keys
    keys = await get_all_keys(session)
    key_count = len(keys)

    async def fetch_key_usage(key: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.scrapfly.io/account?key={key}",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("subscription", {}).get("usage", {}).get("scrape", {})
                    used = usage.get("current", 0)
                    limit = usage.get("limit", CREDITS_PER_KEY)
                    remaining = usage.get("remaining", max(0, limit - used))
                    return {"ok": True, "used": used, "limit": limit, "remaining": remaining}
                logger.warning("scrapfly_account_api_failed", key=key[:20], status=resp.status_code)
        except Exception as e:
            logger.warning("scrapfly_account_api_error", key=key[:20], error=str(e))
        return {"ok": False, "used": 0, "limit": CREDITS_PER_KEY, "remaining": CREDITS_PER_KEY}

    results = await asyncio.gather(*[fetch_key_usage(k) for k in keys])
    total_used = sum(r["used"] for r in results)
    total_credits = key_count * CREDITS_PER_KEY
    remaining = max(0, total_credits - total_used)
    scrapes_possible = remaining // COST_PER_SCRAPE if COST_PER_SCRAPE > 0 else 0

    per_key_remaining = []
    per_key_summary = []
    for key, result in zip(keys, results):
        short = key[:20]
        per_key_remaining.append({
            "key_preview": short + "...",
            "full_key": key,
            "used": result["used"],
            "remaining": result["remaining"],
            "status": "tracked" if result["ok"] else "unreachable",
        })
        per_key_summary.append({
            "key": short + "...",
            "used": result["used"],
            "remaining": result["remaining"],
            "status": "tracked" if result["ok"] else "unreachable",
        })

    return {
        "total_cost": total_used,
        "total_requests": total_used,
        "avg_cost_per_request": round(total_used / key_count, 1) if key_count > 0 else 0,
        "cost_per_product": COST_PER_SCRAPE,
        "remaining_credits": remaining,
        "has_usage_data": total_used > 0,
        "monthly_budget": total_credits,
        "budget_left": remaining,
        "scrapes_remaining_budget": scrapes_possible,
        "scrapes_remaining_actual": scrapes_possible,
        "per_key_summary": per_key_summary,
        "products_possible": scrapes_possible,
        "per_key": {},
        "keys": per_key_remaining,
        "key_count": key_count,
        "total_credits": total_credits,
        "successful_scrapes": total_used,
        "cost_per_scrape": COST_PER_SCRAPE,
    }


@router.get("/scrapfly/keys", summary="List all Scrapfly API keys")
async def list_scrapfly_keys(
    session: AsyncSession = Depends(get_session),
):
    import asyncio
    import httpx

    from services.scrapfly_key_manager import get_all_keys
    keys = await get_all_keys(session)

    async def fetch_key_info(key: str) -> dict:
        short = key[:20]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.scrapfly.io/account?key={key}",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("subscription", {}).get("usage", {}).get("scrape", {})
                    used = usage.get("current", 0)
                    remaining = usage.get("remaining", 0)
                    return {"key_preview": short + "...", "full_key": key, "used": used, "remaining": remaining, "status": "active"}
        except Exception as e:
            logger.warning("scrapfly_key_info_error", key=short, error=str(e))
        return {"key_preview": short + "...", "full_key": key, "used": 0, "remaining": None, "status": "unreachable"}

    results = await asyncio.gather(*[fetch_key_info(k) for k in keys])
    return {"keys": results, "total": len(results)}


@router.post("/scrapfly/keys", summary="Add a Scrapfly API key")
async def add_scrapfly_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    key = body.get("key", "").strip()
    if not key or not key.startswith("scp-"):
        raise HTTPException(status_code=400, detail="Invalid Scrapfly API key format")
    from services.scrapfly_key_manager import add_key

    is_new = await add_key(key, session)

    # Clear quota-exhausted flag so waiting workers resume
    try:
        await redis.delete("scrapfly:quota_exhausted")
        await redis.delete("scrapfly:quota_notified_at")
        logger.info("scrapfly_quota_flag_cleared_on_key_add")
    except Exception:
        pass

    return {"status": "added", "key_preview": key[:20] + "...", "is_new": is_new}


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


@router.delete("/data/clear-all", summary="Clear all scraped data, products, jobs, and assets for a fresh start")
async def clear_all_data(
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Deletes all product links, jobs, assets, and Redis batch data to start fresh."""
    deleted_product_links = (await session.execute(delete(ProductLink))).rowcount
    deleted_jobs = (await session.execute(delete(Job))).rowcount
    deleted_assets = (await session.execute(delete(Asset))).rowcount

    # Clear all Redis keys related to batches
    import re
    keys_to_delete = []
    async for key in redis.scan_iter(match="batch:*"):
        keys_to_delete.append(key)
    if keys_to_delete:
        await redis.delete(*keys_to_delete)

    await session.commit()

    logger.info("clear_all_data", product_links=deleted_product_links, jobs=deleted_jobs, assets=deleted_assets, redis_keys=len(keys_to_delete))
    return {
        "status": "cleared",
        "deleted_product_links": deleted_product_links,
        "deleted_jobs": deleted_jobs,
        "deleted_assets": deleted_assets,
        "deleted_redis_keys": len(keys_to_delete),
        "message": "All data cleared. Ready for a fresh start.",
    }


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
