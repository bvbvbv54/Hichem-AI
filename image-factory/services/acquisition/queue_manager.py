from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import redis.asyncio as redis_async

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.models import AcquisitionJob, FailureType

logger = get_logger(__name__)

QUEUE_HIGH = "acquisition:queue:high"
QUEUE_NORMAL = "acquisition:queue:normal"
QUEUE_RETRY = "acquisition:queue:retry"
QUEUE_DEAD_LETTER = "acquisition:queue:dead_letter"
DEDUP_PREFIX = "acquisition:dedup:"
CHECKPOINT_PREFIX = "acquisition:checkpoint:"
RESTRICTED_PREFIX = "acquisition:restricted:"
MAX_RETRIES = 3


class AcquisitionQueue:
    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def enqueue(self, job: AcquisitionJob, priority: bool = False) -> bool:
        redis_conn = await self._get_redis()
        url_hash = hashlib.sha256(job.url.encode()).hexdigest()
        deduped = await redis_conn.setnx(f"{DEDUP_PREFIX}{url_hash}", "1")
        if not deduped:
            logger.info("job_already_queued", url=job.url)
            return False
        await redis_conn.expire(f"{DEDUP_PREFIX}{url_hash}", 86400)
        queue = QUEUE_HIGH if priority else QUEUE_NORMAL
        await redis_conn.lpush(queue, self._serialize(job))
        logger.info("job_enqueued", url=job.url, queue=queue)
        return True

    async def dequeue(self, timeout: int = 5) -> AcquisitionJob | None:
        redis_conn = await self._get_redis()
        result = await redis_conn.brpop([QUEUE_HIGH, QUEUE_NORMAL], timeout=timeout)
        if result is None:
            return None
        queue, data = result
        return self._deserialize(data)

    async def retry(self, job: AcquisitionJob) -> None:
        redis_conn = await self._get_redis()
        job.attempts += 1
        if job.attempts >= MAX_RETRIES:
            await redis_conn.lpush(QUEUE_DEAD_LETTER, self._serialize(job))
            logger.info("job_dead_letter", url=job.url, attempts=job.attempts)
        else:
            await redis_conn.lpush(QUEUE_RETRY, self._serialize(job))
            logger.info("job_queued_retry", url=job.url, attempt=job.attempts)

    async def is_restricted(self, domain: str) -> bool:
        redis_conn = await self._get_redis()
        return await redis_conn.exists(f"{RESTRICTED_PREFIX}{domain}")

    async def mark_restricted(self, domain: str) -> None:
        redis_conn = await self._get_redis()
        await redis_conn.setex(f"{RESTRICTED_PREFIX}{domain}", 3600, str(int(__import__("time").time())))
        logger.warning("domain_restricted", domain=domain)

    async def save_checkpoint(self, job_id: str, checkpoint: dict) -> None:
        redis_conn = await self._get_redis()
        await redis_conn.setex(f"{CHECKPOINT_PREFIX}{job_id}", 86400, json.dumps(checkpoint))

    async def load_checkpoint(self, job_id: str) -> dict:
        redis_conn = await self._get_redis()
        data = await redis_conn.get(f"{CHECKPOINT_PREFIX}{job_id}")
        if data:
            return json.loads(data)
        return {}

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def _serialize(self, job: AcquisitionJob) -> str:
        return json.dumps({
            "job_id": job.job_id,
            "url": job.url,
            "max_images": job.max_images,
            "priority": job.priority,
            "created_at": job.created_at.isoformat(),
            "attempts": job.attempts,
            "last_error": job.last_error,
            "checkpoint": job.checkpoint,
        })

    def _deserialize(self, data: str) -> AcquisitionJob:
        obj = json.loads(data)
        return AcquisitionJob(
            job_id=obj["job_id"],
            url=obj["url"],
            max_images=obj.get("max_images", 10),
            priority=obj.get("priority", 0),
            created_at=datetime.fromisoformat(obj["created_at"]) if "created_at" in obj else datetime.utcnow(),
            attempts=obj.get("attempts", 0),
            last_error=obj.get("last_error"),
            checkpoint=obj.get("checkpoint", {}),
        )
