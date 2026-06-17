from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import IntelligenceEventType, IntelligenceEvent

logger = get_logger(__name__)

INTELLIGENCE_CHANNEL = "intelligence:events"
INTELLIGENCE_EVENT_PREFIX = "intel:event:"


class EventEmitter:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def emit(
        self,
        event_type: IntelligenceEventType,
        marketplace: str,
        data: dict[str, Any],
    ) -> IntelligenceEvent:
        redis_conn = await self._get_redis()
        event = IntelligenceEvent(
            event_type=event_type,
            marketplace=marketplace,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
        )
        try:
            payload = json.dumps(event.to_dict())
            await redis_conn.publish(INTELLIGENCE_CHANNEL, payload)
        except Exception as exc:
            logger.warning("event_publish_failed", type=event_type.value, error=str(exc))
        return event

    async def emit_raw(
        self,
        event_type: str,
        marketplace: str,
        data: dict[str, Any],
    ) -> None:
        try:
            et = IntelligenceEventType(event_type)
        except ValueError:
            logger.warning("unknown_event_type", type=event_type)
            return
        await self.emit(et, marketplace, data)

    async def get_recent_events(
        self,
        marketplace: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        redis_conn = await self._get_redis()
        keys = await redis_conn.keys(f"{INTELLIGENCE_EVENT_PREFIX}*")
        events: list[dict[str, Any]] = []
        for key in sorted(keys, reverse=True)[:limit * 2]:
            k = key.decode() if isinstance(key, bytes) else key
            data = await redis_conn.get(k)
            if data:
                try:
                    event = json.loads(data)
                    if marketplace and event.get("marketplace") != marketplace:
                        continue
                    if event_type and event.get("type") != event_type:
                        continue
                    events.append(event)
                except json.JSONDecodeError:
                    pass
        return events[:limit]

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
