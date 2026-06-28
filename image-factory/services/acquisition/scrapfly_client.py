from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from configs.logging import get_logger
from configs.settings import settings
from services.scrapfly_rotation import LEASE_RENEWAL_INTERVAL

logger = get_logger(__name__)

SCRAPFLY_BASE = "https://api.scrapfly.io/scrape"
SCRAPFLY_SEM_KEY = "scrapfly:semaphore"
SCRAPFLY_QUOTA_EXHAUSTED_KEY = "scrapfly:quota_exhausted"
QUOTA_WAIT_MAX = 86400

_RESET_DATES_CACHE: dict[str, str] = {}


class ScrapflyClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._redis = None
        self._rotation: Any = None
        self._recovery: Any = None
        self._states_loaded = False
        self._last_recovery_run: float = 0

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def _ensure_rotation(self, redis_conn):
        if self._rotation is None:
            from services.scrapfly_rotation import KeyStateManager, RecoveryScheduler
            self._rotation = KeyStateManager(redis_conn)
            self._recovery = RecoveryScheduler(redis_conn, self._rotation)
        return self._rotation, self._recovery

    async def _load_reset_dates(self, keys: list[str] | None = None) -> dict[str, str]:
        global _RESET_DATES_CACHE
        try:
            from services.scrapfly_key_manager import _KEY_RESET_DATES, _infer_reset_date
            merged = dict(_KEY_RESET_DATES)
            if keys:
                for k in keys:
                    if k not in merged:
                        merged[k] = _infer_reset_date(k)
            _RESET_DATES_CACHE.clear()
            _RESET_DATES_CACHE.update(merged)
        except Exception:
            pass
        return _RESET_DATES_CACHE

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

    async def _is_quota_exhausted(self, redis_conn) -> bool:
        try:
            val = await redis_conn.get(SCRAPFLY_QUOTA_EXHAUSTED_KEY)
            return val is not None
        except Exception:
            return False

    async def _mark_quota_exhausted(self, redis_conn) -> None:
        try:
            await redis_conn.setex(SCRAPFLY_QUOTA_EXHAUSTED_KEY, 86400, str(time.time()))
        except Exception:
            pass

    async def _clear_quota_exhausted(self, redis_conn) -> None:
        try:
            await redis_conn.delete(SCRAPFLY_QUOTA_EXHAUSTED_KEY)
        except Exception:
            pass

    async def _run_recovery(self, redis_conn, reset_dates: dict[str, str] | None = None) -> None:
        now = time.time()
        if now - self._last_recovery_run < 600:
            return
        self._last_recovery_run = now
        try:
            rotation, recovery = await self._ensure_rotation(redis_conn)
            keys = await self._get_keys()
            if keys and reset_dates is None:
                reset_dates = await self._load_reset_dates(keys)
            if keys and not self._states_loaded:
                await rotation.load_all_states(keys, reset_dates)
                self._states_loaded = True
            revived = await recovery.run_recovery_cycle(keys, reset_dates)
            if revived:
                logger.info("recovery_revived_keys", count=len(revived), keys=revived)
        except Exception as e:
            logger.warning("recovery_run_failed", error=str(e))

    async def _wait_for_quota(self, url: str, render_js: bool, country: str | None, redis_conn) -> str | None:
        """Wait loop with recovery checks. Returns content or None."""
        start = time.time()
        poll = settings.scrapfly_quota_poll_interval
        logger.warning("scrapfly_quota_exhausted_waiting", url=url, poll_interval=poll, max_wait=QUOTA_WAIT_MAX)

        rotation, recovery = await self._ensure_rotation(redis_conn)

        while time.time() - start < QUOTA_WAIT_MAX:
            await asyncio.sleep(poll)

            keys = await self._get_keys()
            reset_dates = await self._load_reset_dates(keys)
            await self._run_recovery(redis_conn, reset_dates)
            if keys:
                if not self._states_loaded:
                    await rotation.load_all_states(keys, reset_dates)
                    self._states_loaded = True

                best = await rotation.select_best_key(keys)
                if best:
                    reserved = await rotation.reserve_key(best)
                    if reserved:
                        logger.info("scrapfly_quota_recovered_best_key", key=best[:20])
                        result = await self._fetch_with_keys([best], url, render_js, country, redis_conn, rotation)
                        await rotation.release_key(best)
                        if result:
                            await self._clear_quota_exhausted(redis_conn)
                            return result

            logger.debug("scrapfly_still_waiting_for_quota", elapsed=round(time.time() - start, 1))

        logger.error("scrapfly_quota_wait_timeout", waited_seconds=QUOTA_WAIT_MAX)
        return None

    async def _fetch_with_keys(self, keys: list[str], url: str, render_js: bool,
                                country: str | None, redis_conn,
                                rotation: Any = None) -> str | None:
        """Core fetch logic using rotation manager for weighted key selection."""
        total_429 = 0
        attempted_keys: set[str] = set()

        for key in keys:
            key_short = key[:20]
            if key_short in attempted_keys:
                continue
            attempted_keys.add(key_short)

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

                if rotation:
                    if resp.status_code == 200:
                        await rotation.record_success(key, cost, remaining, remaining_project)
                    else:
                        error_msg = data.get("error", data.get("message", str(resp.status_code)))
                        await rotation.record_failure(key, resp.status_code, error_msg)

                if resp.status_code == 401:
                    logger.warning("scrapfly_unauthorized", key=key_short)
                    continue

                if resp.status_code == 429:
                    total_429 += 1
                    await asyncio.sleep(random.uniform(2, 5))
                    continue

                if resp.status_code != 200:
                    error = data.get("error", data.get("message", str(resp.status_code)))
                    logger.warning("scrapfly_error", key=key_short, error=error)
                    continue

                result = data.get("result", {})
                content = result.get("content")
                if content:
                    logger.info("scrapfly_success", url=url, js=render_js, cost=cost, key=key_short)
                    return content

                logger.warning("scrapfly_no_content", url=url)
            except Exception as e:
                logger.warning("scrapfly_exception", key=key_short, error=str(e))
                if rotation:
                    await rotation.record_failure(key, 0, str(e))
                await asyncio.sleep(random.uniform(1, 3))
                continue

        if rotation:
            states = rotation._local_states
            await rotation.update_metrics(list(states.values()))

        if total_429 > 0 and total_429 == len(attempted_keys):
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

        rotation, recovery = await self._ensure_rotation(redis_conn)

        keys = await self._get_keys()
        reset_dates = await self._load_reset_dates(keys)

        await self._run_recovery(redis_conn, reset_dates)

        if not self._states_loaded:
            if keys:
                await rotation.load_all_states(keys, reset_dates)
                self._states_loaded = True

        if await self._is_quota_exhausted(redis_conn):
            logger.info("scrapfly_quota_already_exhausted_entering_wait")
            return await self._wait_for_quota(url, render_js, country, redis_conn)

        await self._acquire_global_sem(redis_conn)
        try:
            if not keys:
                logger.warning("scrapfly_no_keys_configured")
                return None

            best = await rotation.select_best_key(keys)
            if not best:
                logger.warning("scrapfly_no_available_keys")
                states = list(rotation._local_states.values())
                cooldown_states = [s for s in states if s.status == "COOLDOWN" and s.cooldown_until]
                if cooldown_states:
                    max_wait = max((s.cooldown_until - time.time()) for s in cooldown_states)
                    wait = min(max_wait + random.uniform(1, 5), 60)
                    logger.info("scrapfly_waiting_for_cooldown", wait_seconds=round(wait, 1))
                    await asyncio.sleep(wait)
                    best = await rotation.select_best_key(keys)
                    if not best:
                        rev_cycle = await recovery.run_recovery_cycle(keys, reset_dates)
                        if rev_cycle:
                            best = await rotation.select_best_key(keys)
                if not best:
                    return None

            reserved = await rotation.reserve_key(best)
            if not reserved:
                logger.debug("scrapfly_key_already_reserved", key=best[:20])
                other = await rotation.select_best_key([k for k in keys if k[:20] != best[:20]])
                if other:
                    best = other
                    reserved = await rotation.reserve_key(best)
                if not reserved:
                    await asyncio.sleep(random.uniform(0.5, 2))
                    return await self.fetch_page(url, render_js, country)

            lease_renewal_task: asyncio.Task | None = None

            async def _renew_lease_loop():
                while True:
                    await asyncio.sleep(LEASE_RENEWAL_INTERVAL)
                    ok = await rotation.renew_lease(best)
                    if not ok:
                        break

            try:
                lease_renewal_task = asyncio.create_task(_renew_lease_loop())
                result = await self._fetch_with_keys([best], url, render_js, country, redis_conn, rotation)
                if result is None:
                    other_key = await rotation.select_best_key([k for k in keys if k[:20] != best[:20]])
                    if other_key:
                        reserved2 = await rotation.reserve_key(other_key)
                        if reserved2:
                            try:
                                if lease_renewal_task:
                                    lease_renewal_task.cancel()
                                lease_renewal_task = asyncio.create_task(_renew_lease_loop())
                                result = await self._fetch_with_keys([other_key], url, render_js, country, redis_conn, rotation)
                            finally:
                                await rotation.release_key(other_key)
                if result is None and await self._is_quota_exhausted(redis_conn):
                    return await self._wait_for_quota(url, render_js, country, redis_conn)
                return result
            finally:
                if lease_renewal_task:
                    lease_renewal_task.cancel()
                await rotation.release_key(best)
        finally:
            await self._release_global_sem(redis_conn)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
