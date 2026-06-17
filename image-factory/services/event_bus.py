from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from configs.settings import settings

CHANNEL = "events"


class EventType(str, Enum):
    JOB_STAGE_CHANGED = "job_stage_changed"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    BATCH_PROGRESS = "batch_progress"
    ACQUISITION_ALERT = "acquisition_alert"
    DRIVE_SAVED = "drive_saved"
    SYSTEM_ALERT = "system_alert"
    NOTIFICATION = "notification"


@dataclass
class PipelineEvent:
    event_type: EventType
    job_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: dict[str, Any] = field(default_factory=dict)


async def publish(event: PipelineEvent) -> None:
    r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
    payload = {
        "type": event.event_type.value,
        "job_id": event.job_id,
        "timestamp": event.timestamp.isoformat(),
        **event.data,
    }
    try:
        await r.publish(CHANNEL, json.dumps(payload))
    finally:
        await r.aclose()


async def subscribe() -> AsyncIterator[PipelineEvent]:
    r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
    pubsub = r.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                try:
                    parsed = json.loads(data)
                    raw_type = parsed.pop("type", "notification")
                    try:
                        event_type = EventType(raw_type)
                    except ValueError:
                        event_type = EventType.NOTIFICATION
                    yield PipelineEvent(
                        event_type=event_type,
                        job_id=parsed.pop("job_id", ""),
                        data=parsed,
                    )
                except json.JSONDecodeError:
                    pass
    finally:
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.close()
        await r.aclose()
