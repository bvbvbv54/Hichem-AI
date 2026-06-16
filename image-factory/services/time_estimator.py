from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

_REDIS_KEY = "time_estimator:durations"
_MAX_DURATIONS = 50


class TimeEstimator:
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def record_stage(self, job_id: str, stage: str, duration_seconds: float) -> None:
        key = f"{_REDIS_KEY}:{stage}"
        entry = json.dumps({"job_id": job_id, "duration": duration_seconds, "ts": datetime.utcnow().isoformat()})
        await self._redis.lpush(key, entry)
        await self._redis.ltrim(key, 0, _MAX_DURATIONS - 1)
        await self._redis.expire(key, 86400 * 7)

    async def estimated_stage_duration(self, stage: str) -> float:
        key = f"{_REDIS_KEY}:{stage}"
        raw = await self._redis.lrange(key, 0, _MAX_DURATIONS - 1)
        if not raw:
            return 0.0
        durations = []
        for item in raw:
            try:
                durations.append(json.loads(item)["duration"])
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        if not durations:
            return 0.0
        return math.ceil(sum(durations) / len(durations))

    async def estimated_total_remaining(self, stages_remaining: list[str]) -> float:
        total = 0.0
        for stage in stages_remaining:
            total += await self.estimated_stage_duration(stage)
        return total
