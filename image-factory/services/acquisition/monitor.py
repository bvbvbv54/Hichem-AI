from __future__ import annotations

import time

import redis.asyncio as redis_async

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.models import AcquisitionResult, FailureType

logger = get_logger(__name__)

METRICS_PREFIX = "acquisition:metrics:"
ALERT_CHANNEL = "acquisition:alerts"
WINDOW_SECONDS = 3600


class AcquisitionMonitor:
    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def record(self, result: AcquisitionResult) -> None:
        redis_conn = await self._get_redis()
        now = int(time.time())
        window_key = f"{now // WINDOW_SECONDS}"
        domain = _domain_from_url(result.url)

        pipe = redis_conn.pipeline()
        key_base = f"{METRICS_PREFIX}{domain}:{window_key}"
        if result.success:
            pipe.incr(f"{key_base}:success_count")
        else:
            pipe.incr(f"{key_base}:failure_count")
        if result.failure_type == FailureType.CAPTCHA:
            pipe.incr(f"{key_base}:captcha_count")
        if result.failure_type == FailureType.BOT_BLOCKED:
            pipe.incr(f"{key_base}:blocked_count")
        pipe.incrbyfloat(f"{key_base}:total_duration_ms", result.duration_ms)
        pipe.expire(key_base, WINDOW_SECONDS + 60)
        await pipe.execute()

        await self._check_alert(domain)

    async def get_stats(self, domain: str) -> dict:
        redis_conn = await self._get_redis()
        now = int(time.time())
        current_window = f"{now // WINDOW_SECONDS}"
        prev_window = f"{(now - WINDOW_SECONDS) // WINDOW_SECONDS}"
        keys = [f"{METRICS_PREFIX}{domain}:{w}" for w in (current_window, prev_window)]
        success = 0
        failure = 0
        captcha = 0
        blocked = 0
        total_ms = 0.0
        for key in keys:
            vals = await redis_conn.mget(
                f"{key}:success_count",
                f"{key}:failure_count",
                f"{key}:captcha_count",
                f"{key}:blocked_count",
                f"{key}:total_duration_ms",
            )
            if vals[0]:
                success += int(vals[0])
            if vals[1]:
                failure += int(vals[1])
            if vals[2]:
                captcha += int(vals[2])
            if vals[3]:
                blocked += int(vals[3])
            if vals[4]:
                total_ms += float(vals[4])
        total = success + failure
        success_rate = (success / total) if total > 0 else 1.0
        avg_duration = (total_ms / total) if total > 0 else 0.0
        return {
            "domain": domain,
            "success_count": success,
            "failure_count": failure,
            "captcha_count": captcha,
            "blocked_count": blocked,
            "total_requests": total,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": round(avg_duration, 2),
        }

    async def _check_alert(self, domain: str) -> None:
        redis_conn = await self._get_redis()
        now = int(time.time())
        recent_window = f"{now // 600}"
        key_base = f"{METRICS_PREFIX}{domain}:{recent_window}"
        pipe = redis_conn.pipeline()
        pipe.expire(key_base, 600 + 60)
        vals = await redis_conn.mget(
            f"{key_base}:success_count",
            f"{key_base}:failure_count",
        )
        success = int(vals[0]) if vals[0] else 0
        failure = int(vals[1]) if vals[1] else 0
        total_10m = success + failure
        if total_10m >= 5:
            rate = success / total_10m
            if rate < settings.scraper_alert_threshold:
                alert = {
                    "domain": domain,
                    "success_rate": round(rate, 4),
                    "threshold": settings.scraper_alert_threshold,
                    "timestamp": now,
                }
                await redis_conn.publish(ALERT_CHANNEL, str(alert))
                logger.warning("acquisition_alert", domain=domain, success_rate=rate)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.replace("www.", "")
