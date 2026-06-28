from __future__ import annotations

import asyncio
import random
import time

import redis.asyncio as redis_async

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

RATE_LIMIT_BLOCK_PREFIX = "ratelimit:blocked:"
RATE_LIMIT_TOKEN_PREFIX = "ratelimit:tokens:"
RATE_LIMIT_REQUESTS_PREFIX = "ratelimit:requests:"
RATE_LIMIT_ERRORS_PREFIX = "ratelimit:errors:"


class DomainRateLimiter:
    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None
        self._local_block_cache: dict[str, float] = {}

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def acquire(self, domain: str) -> None:
        redis_conn = await self._get_redis()
        now = time.time()

        cached_block = self._local_block_cache.get(domain, 0)
        if now < cached_block:
            wait = cached_block - now + random.uniform(0.5, 2)
            logger.info("domain_backoff_cached", domain=domain, wait_seconds=round(wait, 1))
            await asyncio.sleep(wait)
            return

        blocked_until = await redis_conn.get(f"{RATE_LIMIT_BLOCK_PREFIX}{domain}")
        if blocked_until:
            blocked_ts = float(blocked_until)
            if now < blocked_ts:
                wait = blocked_ts - now + random.uniform(0.5, 2)
                self._local_block_cache[domain] = blocked_ts
                logger.info("domain_backoff", domain=domain, wait_seconds=round(wait, 1))
                await asyncio.sleep(wait)
                return
            else:
                await redis_conn.delete(f"{RATE_LIMIT_BLOCK_PREFIX}{domain}")

        await self._redis_token_acquire(redis_conn, domain)

    async def _redis_token_acquire(self, redis_conn: redis_async.Redis, domain: str) -> None:
        key = f"{RATE_LIMIT_TOKEN_PREFIX}{domain}"
        now = time.time()
        rate = settings.scraper_default_rps
        burst = settings.scraper_max_burst

        last = await redis_conn.get(key)
        if last is not None:
            parts = last.decode().split(":")
            last_tokens = float(parts[0])
            last_time = float(parts[1])
            elapsed = now - last_time
            tokens = min(burst, last_tokens + elapsed * rate)
        else:
            tokens = burst

        if tokens < 1:
            wait = (1.0 - tokens) / rate
            wait = min(wait, 10)
            await asyncio.sleep(wait + random.uniform(0.1, 0.5))
            tokens = min(burst, tokens + wait * rate)

        tokens = max(0, tokens - 1)
        await redis_conn.set(key, f"{tokens}:{now}")

        req_key = f"{RATE_LIMIT_REQUESTS_PREFIX}{domain}"
        await redis_conn.zadd(req_key, {f"{now}:{random.random()}": now + 120})
        await redis_conn.zremrangebyscore(req_key, "-inf", now - 120)

    async def record_error(self, domain: str) -> None:
        redis_conn = await self._get_redis()
        now = time.time()
        err_key = f"{RATE_LIMIT_ERRORS_PREFIX}{domain}"
        await redis_conn.zadd(err_key, {f"{now}:{random.random()}": now + 120})
        await redis_conn.zremrangebyscore(err_key, "-inf", now - 120)

        recent_errors = await redis_conn.zcard(err_key)
        req_key = f"{RATE_LIMIT_REQUESTS_PREFIX}{domain}"
        recent_requests = await redis_conn.zcard(req_key)

        total_recent = recent_errors + recent_requests
        if total_recent > 5 and recent_errors / max(total_recent, 1) > 0.4:
            logger.info("rate_halved", domain=domain)

    async def record_success(self, domain: str) -> None:
        redis_conn = await self._get_redis()
        now = time.time()
        err_key = f"{RATE_LIMIT_ERRORS_PREFIX}{domain}"
        await redis_conn.zremrangebyscore(err_key, "-inf", now - 300)
        remaining = await redis_conn.zcard(err_key)
        if remaining == 0:
            logger.info("rate_restored", domain=domain, rate=settings.scraper_default_rps)

    async def block_domain(self, domain: str, duration_s: float) -> None:
        redis_conn = await self._get_redis()
        until = time.time() + duration_s
        await redis_conn.setex(f"{RATE_LIMIT_BLOCK_PREFIX}{domain}", int(duration_s) + 10, str(until))
        self._local_block_cache[domain] = until
        logger.info("domain_blocked", domain=domain, duration_seconds=duration_s)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
