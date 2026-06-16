from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import redis.asyncio as redis_async

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


class DomainRateLimiter:
    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None
        self._local_buckets: dict[str, _TokenBucket] = defaultdict(_TokenBucket)
        self._domain_error_counts: dict[str, list[float]] = defaultdict(list)
        self._domain_blocked_until: dict[str, float] = {}

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def acquire(self, domain: str) -> None:
        blocked_until = self._domain_blocked_until.get(domain, 0.0)
        now = time.time()
        if now < blocked_until:
            wait = blocked_until - now
            logger.info("domain_backoff", domain=domain, wait_seconds=wait)
            await asyncio.sleep(wait)
        await self._local_buckets[domain].acquire()

    async def record_error(self, domain: str) -> None:
        now = time.time()
        errors = self._domain_error_counts[domain]
        errors.append(now)
        cutoff = now - 60.0
        self._domain_error_counts[domain] = [t for t in errors if t > cutoff]
        recent_count = len(self._domain_error_counts[domain])
        total_recent = recent_count + self._local_buckets[domain].total_requests_in_window(60.0)
        if total_recent > 0 and recent_count / max(total_recent, 1) > 0.2:
            self._local_buckets[domain].halve_rate()

    async def record_success(self, domain: str) -> None:
        errors = self._domain_error_counts.get(domain, [])
        now = time.time()
        cutoff = now - 300.0
        self._domain_error_counts[domain] = [t for t in errors if t > cutoff]
        if not self._domain_error_counts[domain]:
            self._local_buckets[domain].restore_rate()

    async def block_domain(self, domain: str, duration_s: float) -> None:
        self._domain_blocked_until[domain] = time.time() + duration_s
        logger.info("domain_blocked", domain=domain, duration_seconds=duration_s)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


class _TokenBucket:
    def __init__(self) -> None:
        self._rate = settings.scraper_default_rps
        self._max_burst = settings.scraper_max_burst
        self._tokens = float(self._max_burst)
        self._last_refill = time.time()
        self._request_times: list[float] = []

    async def acquire(self) -> None:
        self._refill()
        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait)
            self._refill()
        self._tokens -= 1.0
        self._request_times.append(time.time())

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._max_burst), self._tokens + elapsed * self._rate)
        self._last_refill = now

    def halve_rate(self) -> None:
        self._rate = max(0.1, self._rate / 2.0)
        logger.info("rate_halved", new_rate=self._rate)

    def restore_rate(self) -> None:
        self._rate = settings.scraper_default_rps
        logger.info("rate_restored", rate=self._rate)

    def total_requests_in_window(self, window_s: float) -> int:
        cutoff = time.time() - window_s
        self._request_times = [t for t in self._request_times if t > cutoff]
        return len(self._request_times)
