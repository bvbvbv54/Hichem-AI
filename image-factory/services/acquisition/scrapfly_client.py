from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

SCRAPFLY_BASE = "https://api.scrapfly.io/scrape"
SCRAPFLY_SEM_KEY = "scrapfly:semaphore"
SCRAPFLY_KEY_COOLDOWN_PREFIX = "scrapfly:cooldown:"
SCRAPFLY_KEY_DEAD_PREFIX = "scrapfly:dead:"
SCRAPFLY_KEY_FAIL_PREFIX = "scrapfly:fails:"
SCRAPFLY_QUOTA_EXHAUSTED_KEY = "scrapfly:quota_exhausted"
SCRAPFLY_QUOTA_EXHAUSTED_KEY_PREFIX = "scrapfly:quota_key_exhausted:"
MAX_CONSECUTIVE_FAILURES = 3
QUOTA_WAIT_INTERVAL = 300        # 5 min between quota polls
QUOTA_WAIT_MAX = 86400           # 24h max wait


class ScrapflyClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._redis = None
        self._session = None
        self._dead_keys: set[str] = set()
        self._quota_exhausted_flag: bool = False

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def _load_dead_keys(self, redis_conn) -> set[str]:
        try:
            from services.scrapfly_key_manager import DEAD_KEYS
            self._dead_keys.update(DEAD_KEYS)
        except Exception:
            pass
        try:
            cursor = 0
            while True:
                cursor, keys = await redis_conn.scan(cursor, match=f"{SCRAPFLY_KEY_DEAD_PREFIX}*")
                for k in keys:
                    key_name = k.decode() if isinstance(k, bytes) else k
                    short = key_name.replace(SCRAPFLY_KEY_DEAD_PREFIX, "")
                    self._dead_keys.add(short)
                if cursor == 0:
                    break
        except Exception:
            pass
        return self._dead_keys

    async def _acquire_global_sem(self, redis_conn) -> bool:
        key = SCRAPFLY_SEM_KEY
        max_conc = settings.scrapfly_max_concurrent
        now = time.time()
        await redis_conn.zremrangebyscore(key, "-inf", now - 30)
        count = await redis_conn.zcard(key)
        if count >= max_conc:
            oldest = await redis_conn.zrange(key, 0, 0, withscores=True)
            if oldest:
                wait = max(0, oldest[0][1] + 15 - now)
                if wait > 0:
                    await asyncio.sleep(wait)
        await redis_conn.zadd(key, {f"{now}:{random.random()}": now + 15})
        return True

    async def _release_global_sem(self, redis_conn) -> None:
        try:
            now = time.time()
            await redis_conn.zremrangebyscore(SCRAPFLY_SEM_KEY, "-inf", now - 30)
        except Exception:
            pass

    async def _is_key_on_cooldown(self, redis_conn, key_short: str) -> bool:
        try:
            remaining = await redis_conn.ttl(f"{SCRAPFLY_KEY_COOLDOWN_PREFIX}{key_short}")
            return remaining > 0
        except Exception:
            return False

    async def _mark_key_cooldown(self, redis_conn, key_short: str, duration: int = 120) -> None:
        try:
            await redis_conn.setex(f"{SCRAPFLY_KEY_COOLDOWN_PREFIX}{key_short}", duration, "1")
        except Exception:
            pass

    async def _mark_key_dead(self, redis_conn, key_short: str) -> None:
        self._dead_keys.add(key_short)
        try:
            await redis_conn.setex(f"{SCRAPFLY_KEY_DEAD_PREFIX}{key_short}", 86400, "1")
            logger.warning("scrapfly_key_marked_dead", key=key_short)
        except Exception:
            pass

    async def _increment_failure(self, redis_conn, key_short: str) -> int:
        try:
            count = await redis_conn.incr(f"{SCRAPFLY_KEY_FAIL_PREFIX}{key_short}")
            await redis_conn.expire(f"{SCRAPFLY_KEY_FAIL_PREFIX}{key_short}", 3600)
            return count
        except Exception:
            return 0

    async def _get_keys(self) -> list[str]:
        try:
            from database.session import async_session
            from services.scrapfly_key_manager import get_all_keys
            async with async_session() as session:
                keys = await get_all_keys(session)
                if keys:
                    return keys
        except Exception as e:
            logger.warning("scrapfly_db_keys_failed", error=str(e))
        return []

    async def _track_usage(self, redis_conn, key: str, cost: int, remaining: int, remaining_project: int):
        try:
            key_short = key[:20]
            await redis_conn.hincrby("scrapfly:usage", f"{key_short}:cost", cost)
            await redis_conn.hset("scrapfly:usage", f"{key_short}:remaining", remaining)
            await redis_conn.hincrby("scrapfly:usage", "total_cost", cost)
            if remaining_project > 0:
                await redis_conn.set("scrapfly:remaining_project", remaining_project)
        except Exception as e:
            logger.warning("scrapfly_track_failed", error=str(e))

    async def _get_budget_remaining(self, redis_conn) -> float:
        try:
            total_cost = await redis_conn.get("scrapfly:usage:total_cost")
            if total_cost:
                return max(0, settings.scrapfly_monthly_budget - float(total_cost))
        except Exception:
            pass
        return settings.scrapfly_monthly_budget

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        return self._client

    async def _get_available_keys(self, redis_conn, keys: list[str]) -> list[str]:
        available = []
        for key in keys:
            key_short = key[:20]
            if key_short in self._dead_keys:
                continue
            if await self._is_key_on_cooldown(redis_conn, key_short):
                continue
            available.append(key)
        try:
            key_remaining = []
            for key in available:
                short = key[:20]
                rem = await redis_conn.hget("scrapfly:usage", f"{short}:remaining")
                remaining = int(rem) if rem else 100000
                key_remaining.append((remaining, key))
            key_remaining.sort(reverse=True)
            return [k for _, k in key_remaining]
        except Exception:
            return available

    async def _is_quota_exhausted(self, redis_conn) -> bool:
        """Check if Scrapfly quota is globally exhausted (all keys out of credits)."""
        try:
            val = await redis_conn.get(SCRAPFLY_QUOTA_EXHAUSTED_KEY)
            return val is not None
        except Exception:
            return self._quota_exhausted_flag

    async def _mark_quota_exhausted(self, redis_conn) -> None:
        """Mark quota exhausted globally with a long TTL (24h)."""
        self._quota_exhausted_flag = True
        try:
            await redis_conn.setex(SCRAPFLY_QUOTA_EXHAUSTED_KEY, 86400, str(time.time()))
        except Exception:
            pass

    async def _clear_quota_exhausted(self, redis_conn) -> None:
        """Clear global quota exhausted flag on successful request."""
        self._quota_exhausted_flag = False
        try:
            await redis_conn.delete(SCRAPFLY_QUOTA_EXHAUSTED_KEY)
        except Exception:
            pass

    async def _wait_for_quota(self, url: str, render_js: bool, country: str | None, redis_conn) -> str | None:
        """Wait loop: poll periodically for new keys or quota reset. Returns content or None."""
        start = time.time()
        poll = settings.scrapfly_quota_poll_interval
        logger.warning("scrapfly_quota_exhausted_waiting",
                       url=url, poll_interval=poll, max_wait=QUOTA_WAIT_MAX)

        from services.scrapfly_key_manager import _is_key_past_reset, DEAD_KEYS, retry_unauthorized_keys

        while time.time() - start < QUOTA_WAIT_MAX:
            await asyncio.sleep(poll)

            # 0. Check if any previously unauthorized keys are now past their retry date
            revived_unauth = await retry_unauthorized_keys(redis_conn)
            if revived_unauth:
                logger.info("scrapfly_unauthorized_keys_revived", revived=len(revived_unauth))

            # 1. Re-fetch keys from DB (new key may have been added via admin)
            keys = await self._get_keys()
            if keys:
                available = await self._get_available_keys(redis_conn, keys)
                if available:
                    logger.info("scrapfly_quota_new_key_found", available=len(available))
                    await self._clear_quota_exhausted(redis_conn)
                    # Retry with the newly available key
                    return await self._fetch_with_keys(available, url, render_js, country, redis_conn)

            # 2. Check if any dead keys have passed their reset date
            revived = [k for k in list(DEAD_KEYS) if _is_key_past_reset(k)]
            if revived:
                for k in revived:
                    DEAD_KEYS.discard(k)
                    logger.info("scrapfly_key_auto_revived", key=k[:20])
                keys = await self._get_keys()
                available = await self._get_available_keys(redis_conn, keys)
                if available:
                    logger.info("scrapfly_quota_reset_revived_keys", revived=len(revived))
                    await self._clear_quota_exhausted(redis_conn)
                    return await self._fetch_with_keys(available, url, render_js, country, redis_conn)

            logger.debug("scrapfly_still_waiting_for_quota", elapsed=round(time.time() - start, 1))

        logger.error("scrapfly_quota_wait_timeout", waited_seconds=QUOTA_WAIT_MAX)
        return None

    async def _fetch_with_keys(self, keys: list[str], url: str, render_js: bool,
                                country: str | None, redis_conn) -> str | None:
        """Core fetch logic — iterate through keys, return first success or None."""
        quota_exhausted_keys: set[str] = set()
        total_429 = 0

        for key in keys:
            key_short = key[:20]
            try:
                client = await self._get_client()
                params: dict[str, Any] = {
                    "key": key,
                    "url": url,
                    "asp": "true",
                }
                if render_js:
                    params["render_js"] = "true"
                if country:
                    params["country"] = country

                await asyncio.sleep(random.uniform(0.3, 1.5))
                resp = await client.get(SCRAPFLY_BASE, params=params)

                cost = int(resp.headers.get("x-scrapfly-api-cost", 0))
                remaining = int(resp.headers.get("x-scrapfly-remaining-api-credit", 0))
                remaining_project = int(resp.headers.get("x-scrapfly-project-remaining-api-credit", 0))
                await self._track_usage(redis_conn, key, cost, remaining, remaining_project)

                data = resp.json()

                if resp.status_code == 401:
                    logger.warning("scrapfly_unauthorized", key=key_short)
                    from services.scrapfly_key_manager import mark_key_unauthorized
                    await mark_key_unauthorized(key, redis_conn)
                    continue

                if resp.status_code == 429:
                    total_429 += 1
                    if remaining_project <= 0:
                        # Quota exhaustion (not just rate limiting)
                        logger.warning("scrapfly_quota_exhausted", key=key_short)
                        quota_exhausted_keys.add(key_short)
                        await self._mark_key_cooldown(redis_conn, key_short, 3600)  # 1h cooldown
                    else:
                        # Rate limiting — short cooldown
                        logger.warning("scrapfly_rate_limited", key=key_short)
                        await self._mark_key_cooldown(redis_conn, key_short, settings.scrapfly_key_cooldown)
                    await asyncio.sleep(random.uniform(2, 5))
                    continue

                if resp.status_code != 200:
                    error = data.get("error", data.get("message", str(resp.status_code)))
                    logger.warning("scrapfly_error", key=key_short, error=error)
                    fail_count = await self._increment_failure(redis_conn, key_short)
                    if fail_count >= MAX_CONSECUTIVE_FAILURES:
                        await self._mark_key_dead(redis_conn, key_short)
                    continue

                result = data.get("result", {})
                content = result.get("content")
                if content:
                    try:
                        await redis_conn.delete(f"{SCRAPFLY_KEY_FAIL_PREFIX}{key_short}")
                    except Exception:
                        pass
                    logger.info("scrapfly_success", url=url, js=render_js, cost=cost)
                    return content

                logger.warning("scrapfly_no_content", url=url)
            except Exception as e:
                logger.warning("scrapfly_exception", key=key_short, error=str(e))
                fail_count = await self._increment_failure(redis_conn, key_short)
                if fail_count >= MAX_CONSECUTIVE_FAILURES:
                    await self._mark_key_dead(redis_conn, key_short)
                await asyncio.sleep(random.uniform(1, 3))
                continue

        # After all keys tried — signal quota exhaustion if all failures were 429 with 0 credit
        if quota_exhausted_keys and len(quota_exhausted_keys) == total_429 and total_429 > 0:
            from services.scrapfly_key_manager import notify_quota_exhausted
            await self._mark_quota_exhausted(redis_conn)
            await notify_quota_exhausted(redis_conn)

        return None

    async def fetch_page(self, url: str, render_js: bool = False, country: str | None = None) -> str | None:
        if not settings.scrapfly_enabled:
            return None

        jitter = random.uniform(0.5, settings.scrapfly_request_jitter)
        await asyncio.sleep(jitter)

        redis_conn = await self._get_redis()

        budget = await self._get_budget_remaining(redis_conn)
        if budget <= 0:
            logger.warning("scrapfly_budget_exhausted")
            return None

        await self._load_dead_keys(redis_conn)

        # Check if we're in quota-exhausted state — enter wait loop immediately
        if await self._is_quota_exhausted(redis_conn):
            logger.info("scrapfly_quota_already_exhausted_entering_wait")
            return await self._wait_for_quota(url, render_js, country, redis_conn)

        await self._acquire_global_sem(redis_conn)
        try:
            keys = await self._get_keys()
            if not keys:
                logger.warning("scrapfly_no_keys_configured")
                return None

            all_keys = keys
            keys = await self._get_available_keys(redis_conn, keys)
            if not keys:
                logger.warning("scrapfly_all_keys_on_cooldown_or_dead")
                cooldown_ttls = []
                for key in all_keys:
                    key_short = key[:20]
                    if key_short in self._dead_keys:
                        continue
                    ttl = await redis_conn.ttl(f"{SCRAPFLY_KEY_COOLDOWN_PREFIX}{key_short}")
                    if ttl > 0:
                        cooldown_ttls.append(ttl)
                if cooldown_ttls:
                    wait = min(max(cooldown_ttls) + random.uniform(1, 5), 60)
                    logger.info("scrapfly_waiting_for_cooldown", wait_seconds=round(wait, 1))
                    await asyncio.sleep(wait)
                    keys = await self._get_keys()
                    keys = await self._get_available_keys(redis_conn, keys)
                    if not keys:
                        return None

            result = await self._fetch_with_keys(keys, url, render_js, country, redis_conn)

            # If quota exhaustion detected and no result, enter wait loop
            if result is None and await self._is_quota_exhausted(redis_conn):
                return await self._wait_for_quota(url, render_js, country, redis_conn)

            return result
        finally:
            await self._release_global_sem(redis_conn)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
