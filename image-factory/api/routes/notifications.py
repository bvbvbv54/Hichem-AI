from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_redis
from configs.logging import get_logger
from services.notifications import get_notification_service, NotificationEvent

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    redis: aioredis.Redis = Depends(get_redis),
):
    service = get_notification_service()
    raw = await redis.lrange("notifications:list:", 0, limit - 1)
    notifications = []
    for nid in raw:
        nid_str = nid.decode() if isinstance(nid, bytes) else nid
        key = f"notifications::{nid_str}"
        data = await redis.get(key)
        if data:
            parsed = json.loads(data) if isinstance(data, bytes) else json.loads(data)
            if unread_only and parsed.get("read"):
                continue
            notifications.append(parsed)
    unread_count = sum(1 for n in notifications if not n.get("read"))
    return {"notifications": notifications, "unread_count": unread_count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"notifications::{notification_id}"
    data = await redis.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif = json.loads(data) if isinstance(data, bytes) else json.loads(data)
    notif["read"] = True
    await redis.setex(key, 86400, json.dumps(notif))
    try:
        from database.session import async_session
        from database.models.notification import Notification
        from sqlalchemy import select
        async with async_session() as session:
            result = await session.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            db_notif = result.scalar_one_or_none()
            if db_notif:
                db_notif.read = True
                await session.commit()
    except Exception as e:
        logger.warning("db_mark_read_failed", notification_id=notification_id, error=str(e))
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(
    redis: aioredis.Redis = Depends(get_redis),
):
    raw = await redis.lrange("notifications:list:", 0, -1)
    count = 0
    for nid in raw:
        nid_str = nid.decode() if isinstance(nid, bytes) else nid
        key = f"notifications::{nid_str}"
        data = await redis.get(key)
        if data:
            notif = json.loads(data) if isinstance(data, bytes) else json.loads(data)
            if not notif.get("read"):
                notif["read"] = True
                await redis.setex(key, 86400, json.dumps(notif))
                count += 1
    try:
        from database.session import async_session
        from database.models.notification import Notification
        from sqlalchemy import update as sql_update
        async with async_session() as session:
            await session.execute(
                sql_update(Notification).values(read=True)
            )
            await session.commit()
    except Exception as e:
        logger.warning("db_mark_all_read_failed", error=str(e))
    return {"status": "all_read", "marked_count": count}
