"""Notification system for tracking job progress via Redis."""

import json
from datetime import datetime
from typing import Optional, Any
from enum import Enum

import redis.asyncio as redis_async
from pydantic import BaseModel, Field

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


class NotificationLevel(str, Enum):
    """Notification severity levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationEvent(BaseModel):
    """A notification event."""
    id: str
    user_id: Optional[str] = None
    type: str
    level: NotificationLevel = NotificationLevel.INFO
    title: str
    message: str
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    data: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False


class NotificationService:
    """Service for publishing and managing notifications."""

    CHANNEL = "notifications"

    def __init__(self):
        self.redis = None

    async def connect(self):
        """Connect to Redis."""
        if not self.redis:
            self.redis = await redis_async.from_url(settings.redis_url)

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.aclose()
            self.redis = None

    async def publish(self, notification: NotificationEvent):
        """Publish notification to Redis pub/sub."""
        await self.connect()
        try:
            payload = notification.model_dump_json()
            await self.redis.publish(self.CHANNEL, payload)
            logger.info("notification_published", type=notification.type, level=notification.level)
        except Exception as e:
            logger.error("notification_publish_failed", error=str(e))

    async def store(self, notification: NotificationEvent):
        """Store notification in Redis for persistence."""
        await self.connect()
        try:
            key = f"notifications:{notification.user_id}:{notification.id}"
            await self.redis.setex(
                key,
                86400,  # 24 hours TTL
                notification.model_dump_json()
            )
            
            # Add to list for pagination
            list_key = f"notifications:list:{notification.user_id}"
            await self.redis.lpush(list_key, notification.id)
            await self.redis.ltrim(list_key, 0, 999)  # Keep last 1000
            
            logger.info("notification_stored", user_id=notification.user_id)
        except Exception as e:
            logger.error("notification_store_failed", error=str(e))

    async def get_notifications(self, user_id: str, limit: int = 100) -> list[NotificationEvent]:
        """Get user's notifications."""
        await self.connect()
        try:
            list_key = f"notifications:list:{user_id}"
            ids = await self.redis.lrange(list_key, 0, limit - 1)
            
            notifications = []
            for notif_id in ids:
                key = f"notifications:{user_id}:{notif_id.decode()}"
                data = await self.redis.get(key)
                if data:
                    notifications.append(NotificationEvent.model_validate_json(data))
            
            return notifications
        except Exception as e:
            logger.error("get_notifications_failed", error=str(e))
            return []

    async def mark_read(self, user_id: str, notification_id: str):
        """Mark notification as read."""
        await self.connect()
        try:
            key = f"notifications:{user_id}:{notification_id}"
            data = await self.redis.get(key)
            if data:
                notif = NotificationEvent.model_validate_json(data)
                notif.read = True
                await self.redis.setex(
                    key,
                    86400,
                    notif.model_dump_json()
                )
                logger.info("notification_marked_read", notification_id=notification_id)
        except Exception as e:
            logger.error("mark_read_failed", error=str(e))


# Global service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create notification service."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def send_notification(
    user_id: str,
    title: str,
    message: str,
    event_type: str = "info",
    level: NotificationLevel = NotificationLevel.INFO,
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    data: Optional[dict] = None,
):
    """Send a notification to user."""
    import uuid
    
    service = get_notification_service()
    
    notification = NotificationEvent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=event_type,
        level=level,
        title=title,
        message=message,
        project_id=project_id,
        run_id=run_id,
        data=data or {},
    )
    
    await service.publish(notification)
    await service.store(notification)
