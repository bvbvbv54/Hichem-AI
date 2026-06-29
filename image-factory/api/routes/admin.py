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
from services.settings_service import get_provider_api_key, set_provider_api_key, get_provider_keys_status, get_setting, set_setting, get_img2img_config, set_img2img_config, get_storage_config, set_storage_config, set_storage_enabled, get_google_api_key, set_google_api_key, get_all_settings
from database.models.asset import Asset

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def admin_stats(
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    from database.models.user import User, Project

    user_count = await session.execute(select(func.count(User.id)))
    total_users = user_count.scalar() or 0

    project_count = await session.execute(select(func.count(Project.id)))
    total_projects = project_count.scalar() or 0

    job_count = await session.execute(select(func.count(Job.id)))
    total_jobs = job_count.scalar() or 0

    worker_active = 0
    try:
        import asyncio
        r2 = await asyncio.wait_for(
            aioredis.from_url(settings.celery_broker_url, socket_connect_timeout=2),
            timeout=2.0,
        )
        try:
            has_workers = await asyncio.wait_for(r2.exists("celery@default"), timeout=2.0)
            if has_workers:
                workers = await asyncio.wait_for(r2.smembers("celery@default"), timeout=2.0)
                worker_active = len(workers)
        except Exception:
            worker_active = 0
        await r2.aclose()
    except Exception:
        pass

    max_concurrency = getattr(settings, "batch_max_concurrent", 4)

    active_jobs = await session.execute(select(func.count(Job.id)).where(Job.status.in_(["processing", "generating", "storing", "delivering"])))
    waiting_jobs = await session.execute(select(func.count(Job.id)).where(Job.status.in_(["pending", "queued"])))
    failed_jobs = await session.execute(select(func.count(Job.id)).where(Job.status == "failed"))
    retry_jobs = await session.execute(select(func.count(Job.id)).where(Job.status == "retrying"))

    active_count = active_jobs.scalar() or 0
    waiting_count = waiting_jobs.scalar() or 0
    failed_count = failed_jobs.scalar() or 0
    retry_count = retry_jobs.scalar() or 0
    total = active_count + waiting_count + failed_count

    queue_stats = {
        "current_length": total,
        "active_jobs": active_count,
        "waiting_jobs": waiting_count,
        "failed_jobs": failed_count,
        "retry_jobs": retry_count,
        "estimated_completion_minutes": total * 2,
        "estimated_wait_minutes": waiting_count * 2,
        "workers_active": worker_active or 4,
    }

    db_status = "healthy"
    try:
        await session.execute(select(1))
    except Exception:
        db_status = "degraded"

    infrastructure = {
        "api": "healthy",
        "worker": "healthy" if worker_active > 0 else "degraded",
        "database": db_status,
        "queue": "healthy",
        "storage": "healthy",
        "delivery": "healthy",
    }

    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_jobs": total_jobs,
        "total_api_usage": 0,
        "worker_stats": {
            "active": worker_active or 4,
            "available": worker_active or 4,
            "max_concurrency": max_concurrency,
        },
        "queue_stats": queue_stats,
        "infrastructure": infrastructure,
    }


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
    processing = await session.execute(
        select(func.count(Job.id)).where(Job.status == "processing")
    )
    pending = await session.execute(
        select(func.count(Job.id)).where(Job.status == "pending")
    )
    failed = await session.execute(
        select(func.count(Job.id)).where(Job.status == "failed")
    )
    dead_letter = await session.execute(
        select(func.count(Job.id)).where(and_(Job.status == "failed", Job.retry_count >= Job.max_retries))
    )

    return {
        "paused": paused is not None and paused == b"1",
        "processing": processing.scalar() or 0,
        "pending": pending.scalar() or 0,
        "failed": failed.scalar() or 0,
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


@router.post("/jobs/retry-all-failed", summary="Requeue all failed jobs")
async def retry_all_failed(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Job).where(Job.status == "failed")
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


@router.put("/provider-keys/replicate", summary="Update Replicate API key for FLUX model access (persisted to DB)")
async def update_replicate_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    if not key.strip().startswith("r8_") and not key.strip().startswith("r8rk_"):
        raise HTTPException(status_code=400, detail="Invalid Replicate API key format — must start with 'r8_'")
    await set_provider_api_key("replicate_api_key", key.strip(), session)
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


@router.put("/settings/cleanup/toggle", summary="Enable or disable local file auto-cleanup")
async def toggle_cleanup(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be a boolean")
    await set_setting("auto_cleanup_local", "true" if enabled else "false", session)
    return {"status": "updated", "auto_cleanup_local": enabled}


async def _resolve_key_status(key: str, ok: bool, remaining: int, redis: aioredis.Redis) -> str:
    """Determine Scrapfly key status: ACTIVE, QUOTA_EXHAUSTED, BANNED, or UNREACHABLE."""
    key_short = key[:20]
    banned = await redis.get(f"scrapfly:banned:{key_short}")
    if banned:
        return "BANNED"
    if not ok:
        return "UNREACHABLE"
    if remaining <= 0:
        return "QUOTA_EXHAUSTED"
    return "ACTIVE"

@router.get("/scrapfly/usage", summary="Get Scrapfly credit usage")
async def get_scrapfly_usage(
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    COST_PER_SCRAPE = 12
    COST_PER_PRODUCT = 12
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
    products_possible = remaining // COST_PER_PRODUCT if COST_PER_PRODUCT > 0 else 0

    per_key_remaining = []
    per_key_summary = []
    for idx, (key, result) in enumerate(zip(keys, results)):
        safe_label = f"Key-{idx + 1}"
        key_remaining = result["remaining"]
        key_products = max(0, key_remaining // COST_PER_PRODUCT)
        key_status = await _resolve_key_status(key, result["ok"], key_remaining, redis)
        per_key_remaining.append({
            "safe_label": safe_label,
            "used": result["used"],
            "remaining": result["remaining"],
            "estimated_scrapes": key_products,
            "cost_per_scrape_estimate": COST_PER_SCRAPE,
            "status": key_status,
        })
        per_key_summary.append({
            "label": safe_label,
            "used": result["used"],
            "remaining": result["remaining"],
            "estimated_scrapes": key_products,
            "status": key_status,
        })

    return {
        "total_cost": total_used,
        "total_requests": total_used,
        "avg_cost_per_request": round(total_used / key_count, 1) if key_count > 0 else 0,
        "cost_per_product": COST_PER_PRODUCT,
        "remaining_credits": remaining,
        "has_usage_data": total_used > 0,
        "monthly_budget": total_credits,
        "budget_left": remaining,
        "scrapes_remaining_budget": products_possible,
        "scrapes_remaining_actual": products_possible,
        "per_key_summary": per_key_summary,
        "products_possible": products_possible,
        "per_key": {},
        "keys": per_key_remaining,
        "key_count": key_count,
        "total_credits": total_credits,
        "successful_scrapes": total_used,
        "cost_per_scrape": COST_PER_SCRAPE,
        "estimated_products": products_possible,
    }


@router.get("/scrapfly/metrics", summary="Get Scrapfly rotation metrics")
async def get_scrapfly_rotation_metrics():
    from services.scrapfly_rotation import KeyStateManager
    from services.acquisition.scrapfly_client import ScrapflyClient
    from configs.settings import settings
    import redis.asyncio as aioredis
    try:
        redis_conn = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        mgr = KeyStateManager(redis_conn)
        metrics = await mgr.get_metrics()
        await redis_conn.aclose()
        return metrics
    except Exception as e:
        from configs.logging import get_logger
        logger = get_logger(__name__)
        logger.warning("scrapfly_metrics_failed", error=str(e))
        return {"error": str(e)}


@router.get("/scrapfly/keys", summary="List all Scrapfly API keys")
async def list_scrapfly_keys(
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    import asyncio
    import httpx

    from services.scrapfly_key_manager import get_all_keys
    keys = await get_all_keys(session)

    async def fetch_key_info(key: str) -> dict:
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
                    return {"ok": True, "used": used, "remaining": remaining}
        except Exception as e:
            logger.warning("scrapfly_key_info_error", key=key[:20], error=str(e))
        return {"ok": False, "used": 0, "remaining": None}

    results = await asyncio.gather(*[fetch_key_info(k) for k in keys])
    enriched = []
    for idx, (key, r) in enumerate(zip(keys, results)):
        safe_label = f"Key-{idx + 1}"
        key_status = await _resolve_key_status(key, r["ok"], r["remaining"] or 0, redis)
        enriched.append({
            "safe_label": safe_label,
            "used": r["used"],
            "remaining": r["remaining"],
            "status": key_status,
        })
    return {"keys": enriched, "total": len(enriched)}


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

    # Auto-verify the key by calling Scrapfly API
    import httpx
    verified_status = "UNKNOWN"
    usage_info = {}
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
                if remaining > 0:
                    verified_status = "ACTIVE"
                else:
                    verified_status = "QUOTA_EXHAUSTED"
                usage_info = {"used": used, "remaining": remaining}
                logger.info("scrapfly_key_verified_active", key=key[:20], remaining=remaining)
            else:
                verified_status = "UNREACHABLE"
                logger.warning("scrapfly_key_verification_failed", key=key[:20], status=resp.status_code)
    except Exception as e:
        verified_status = "UNREACHABLE"
        logger.warning("scrapfly_key_verification_error", key=key[:20], error=str(e))

    # Initialize rotation state for the new key
    try:
        from services.scrapfly_rotation import KeyStateManager, DEFAULT_CREDITS
        mgr = KeyStateManager(redis)
        key_short = key[:20]
        from services.scrapfly_rotation import KeyState
        credits = usage_info.get("remaining", DEFAULT_CREDITS) if verified_status in ("ACTIVE", "QUOTA_EXHAUSTED") else DEFAULT_CREDITS
        rotation_status = "ACTIVE" if verified_status in ("ACTIVE", "QUOTA_EXHAUSTED") else "UNKNOWN"
        state = KeyState(key=key_short, status=rotation_status, estimated_credits_remaining=credits)
        await mgr._save_state(state)
        logger.info("scrapfly_rotation_state_initialized_for_new_key", key=key_short)
    except Exception as e:
        logger.warning("scrapfly_rotation_init_failed", error=str(e))

    # Invalidate the in-memory reset-dates cache so next fetch picks up the new key
    try:
        from services.acquisition.scrapfly_client import _RESET_DATES_CACHE
        _RESET_DATES_CACHE.clear()
    except Exception:
        pass

    return {
        "status": "added",
        "is_new": is_new,
        "verified": verified_status,
        "usage": usage_info,
    }


async def _resolve_key_by_label(safe_label: str, session: AsyncSession) -> str | None:
    """Resolve a safe label (e.g. 'Key-3') to the actual key value from the DB."""
    if not safe_label.startswith("Key-"):
        return None
    try:
        idx = int(safe_label.split("-", 1)[1]) - 1
        if idx < 0:
            return None
    except ValueError:
        return None
    from services.scrapfly_key_manager import get_all_keys
    keys = await get_all_keys(session)
    if idx >= len(keys):
        return None
    return keys[idx]


@router.delete("/scrapfly/keys", summary="Remove a Scrapfly API key")
async def remove_scrapfly_key(
    body: dict,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    key_id = body.get("key_id", "").strip()
    if not key_id:
        raise HTTPException(status_code=400, detail="key_id is required (e.g. 'Key-1')")
    key = await _resolve_key_by_label(key_id, session)
    if not key:
        raise HTTPException(status_code=404, detail=f"No key found for '{key_id}'")
    from services.scrapfly_key_manager import remove_key

    await remove_key(key, session)

    # Clean up rotation state and banned flag for the removed key
    try:
        from services.scrapfly_rotation import STATE_KEY, RESERVATION_KEY
        key_short = key[:20]
        await redis.delete(f"{STATE_KEY}{key_short}")
        await redis.delete(f"{RESERVATION_KEY}{key_short}")
        await redis.delete(f"scrapfly:banned:{key_short}")
        logger.info("scrapfly_rotation_state_cleaned_for_removed_key", key=key_short)
    except Exception as e:
        logger.warning("scrapfly_rotation_cleanup_failed", error=str(e))

    return {"status": "removed", "key_id": key_id}


@router.post("/scrapfly/keys/{key_id}/ban", summary="Mark a Scrapfly key as banned")
async def ban_scrapfly_key(
    key_id: str,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    key = await _resolve_key_by_label(key_id, session)
    if not key:
        raise HTTPException(status_code=404, detail=f"No key found for '{key_id}'")
    key_short = key[:20]
    await redis.set(f"scrapfly:banned:{key_short}", "1")
    logger.info("scrapfly_key_banned", key=key_short)
    return {"status": "banned", "key_id": key_id}


@router.post("/scrapfly/keys/{key_id}/unban", summary="Unmark a banned Scrapfly key")
async def unban_scrapfly_key(
    key_id: str,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    key = await _resolve_key_by_label(key_id, session)
    if not key:
        raise HTTPException(status_code=404, detail=f"No key found for '{key_id}'")
    key_short = key[:20]
    await redis.delete(f"scrapfly:banned:{key_short}")
    logger.info("scrapfly_key_unbanned", key=key_short)
    return {"status": "unbanned", "key_id": key_id}


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
