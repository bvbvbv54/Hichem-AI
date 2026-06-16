from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
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
