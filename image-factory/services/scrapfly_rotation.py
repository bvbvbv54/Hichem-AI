from __future__ import annotations

import asyncio
import json
import math
import os
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

KeyStatus = Literal["ACTIVE", "SUSPECT", "COOLDOWN", "EXHAUSTED", "UNKNOWN", "DISABLED", "DRAINING"]

REDIS_PREFIX = "scrapfly:rotation:"
STATE_KEY = f"{REDIS_PREFIX}state"
COST_HISTORY_KEY = f"{REDIS_PREFIX}cost_history:"
LOCK_KEY = f"{REDIS_PREFIX}lock:"
METRICS_KEY = f"{REDIS_PREFIX}metrics"
RESERVATION_KEY = f"{REDIS_PREFIX}reservation:"

DEFAULT_CREDITS = 1000
DEFAULT_AVG_COST = 12
COST_HISTORY_MAX = 100
COOLDOWN_SECONDS = 120
EXHAUSTED_COOLDOWN = 3600
MAX_CONSECUTIVE_FAILURES = 3
MAX_SUSPECT_FAILURES = 3
SUSPECT_WINDOW = 600
COOLDOWN_AFTER_SUSPECT_FAILURES = 5
RESERVATION_TTL = 120
LEASE_RENEWAL_INTERVAL = 30
RECOVERY_INTERVAL = 21600
MONTHLY_CHECK_INTERVAL = 86400
MIN_RESTORE_THRESHOLD = 500
CREDITS_BURN_WINDOW_HOURS = 1
DRAINING_THRESHOLD_HOURS = 24
WORKER_ID = os.environ.get("HOSTNAME", os.environ.get("COMPUTERNAME", "unknown-worker"))

EMERGENCY_CREDITS = 200


@dataclass
class KeyState:
    key: str
    status: KeyStatus = "UNKNOWN"
    available_credits: int = DEFAULT_CREDITS
    estimated_credits_remaining: int = DEFAULT_CREDITS
    reset_date: str | None = None
    last_success: float | None = None
    last_failure: float | None = None
    consecutive_failures: int = 0
    suspect_failures: int = 0
    suspect_window_start: float | None = None
    cooldown_until: float | None = None
    average_cost: float = DEFAULT_AVG_COST
    requests_made: int = 0
    last_detected_reset: str | None = None
    next_estimated_reset: str | None = None
    projected_hours_left: float | None = None
    draining: bool = False
    success_rate: float = 1.0
    credits_burn_history: list[tuple[float, int]] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        if self.status not in ("ACTIVE", "SUSPECT", "DRAINING"):
            return False
        if self.cooldown_until and time.time() < self.cooldown_until:
            return False
        if self.estimated_credits_remaining <= 0:
            return False
        return True

    @property
    def weight(self) -> float:
        if not self.is_available:
            return -1.0

        credits_score = self.estimated_credits_remaining / DEFAULT_CREDITS

        if self.last_success:
            mins_since = (time.time() - self.last_success) / 60.0
            recency_score = math.exp(-mins_since / 60.0)
        else:
            recency_score = 0.1

        usage_score = max(0.1, 1.0 - (self.requests_made / 1000))

        total = self.consecutive_failures + max(0, self.requests_made - 5)
        health_score = self.success_rate if total == 0 else self.success_rate * (1.0 - min(1.0, total / 20.0))

        draining_penalty = 0.3 if self.draining else 0.0

        raw = credits_score * 0.4 + recency_score * 0.2 + usage_score * 0.2 + health_score * 0.2
        return raw * (1.0 - draining_penalty)


class CreditEstimator:
    """Tracks per-key scrape cost history and provides rolling statistics."""

    def __init__(self, redis_conn: Any) -> None:
        self._redis = redis_conn

    async def record_cost(self, key_short: str, cost: int) -> None:
        try:
            key = f"{COST_HISTORY_KEY}{key_short}"
            await self._redis.lpush(key, cost)
            await self._redis.ltrim(key, 0, COST_HISTORY_MAX - 1)
            await self._redis.expire(key, 86400 * 7)
        except Exception as e:
            logger.warning("cost_record_failed", key=key_short, error=str(e))

    async def get_stats(self, key_short: str) -> dict[str, float]:
        try:
            key = f"{COST_HISTORY_KEY}{key_short}"
            costs = await self._redis.lrange(key, 0, -1)
            if not costs:
                return {"avg": DEFAULT_AVG_COST, "p50": DEFAULT_AVG_COST, "p95": DEFAULT_AVG_COST, "count": 0}
            values = [int(c) for c in costs]
            values.sort()
            return {
                "avg": round(statistics.mean(values), 1),
                "p50": round(statistics.median(values), 1),
                "p95": round(values[int(len(values) * 0.95)] if len(values) > 1 else values[-1], 1),
                "count": len(values),
            }
        except Exception as e:
            logger.warning("cost_stats_failed", key=key_short, error=str(e))
            return {"avg": DEFAULT_AVG_COST, "p50": DEFAULT_AVG_COST, "p95": DEFAULT_AVG_COST, "count": 0}


class EmergencyCache:
    """In-memory emergency cache used when Redis is unavailable."""

    def __init__(self) -> None:
        self._states: dict[str, KeyState] = {}
        self._redis_down_since: float | None = None
        self._write_queue: list[dict] = []

    def get(self, key_short: str) -> KeyState | None:
        return self._states.get(key_short)

    def set(self, state: KeyState) -> None:
        self._states[state.key] = state

    def set_redis_down(self) -> None:
        if self._redis_down_since is None:
            self._redis_down_since = time.time()

    def clear_redis_down(self) -> None:
        self._redis_down_since = None

    @property
    def is_active(self) -> bool:
        return self._redis_down_since is not None


class KeyStateManager:
    """Manages per-key state with Redis persistence, weighted selection, and concurrency safety."""

    def __init__(self, redis_conn: Any) -> None:
        self._redis = redis_conn
        self._estimator = CreditEstimator(redis_conn)
        self._local_states: dict[str, KeyState] = {}
        self._emergency = EmergencyCache()

    async def _redis_available(self) -> bool:
        if self._emergency.is_active:
            if time.time() - self._emergency._redis_down_since > 30:
                try:
                    await self._redis.ping()
                    self._emergency.clear_redis_down()
                    await self._flush_emergency_queue()
                    return True
                except Exception:
                    self._emergency.set_redis_down()
                    return False
            return False
        return True

    async def _flush_emergency_queue(self) -> None:
        for entry in self._emergency._write_queue:
            try:
                await self._redis.hset(entry["key"], mapping=entry["mapping"])
                if "expire" in entry:
                    await self._redis.expire(entry["key"], entry["expire"])
            except Exception:
                pass
        self._emergency._write_queue.clear()

    async def _hset(self, key: str, mapping: dict, expire: int | None = None) -> None:
        try:
            await self._redis.hset(key, mapping=mapping)
            if expire:
                await self._redis.expire(key, expire)
        except Exception:
            self._emergency.set_redis_down()
            self._emergency._write_queue.append({"key": key, "mapping": mapping, "expire": expire})

    async def _hgetall(self, key: str) -> dict:
        try:
            return await self._redis.hgetall(key)
        except Exception:
            self._emergency.set_redis_down()
            cached = self._emergency.get(key)
            if cached:
                return {"status": cached.status}
            return {}

    async def _get(self, key: str) -> Any | None:
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def _set(self, key: str, value: Any, nx: bool = False, ex: int | None = None) -> bool:
        try:
            return bool(await self._redis.set(key, value, nx=nx, ex=ex))
        except Exception:
            self._emergency.set_redis_down()
            return False

    async def _delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            pass

    async def load_all_states(self, keys: list[str], reset_dates: dict[str, str]) -> list[KeyState]:
        states: list[KeyState] = []
        for key in keys:
            state = await self._load_state(key, reset_dates.get(key))
            states.append(state)
            self._local_states[key[:20]] = state
            self._emergency.set(state)
        return states

    async def _load_state(self, key: str, reset_date: str | None) -> KeyState:
        key_short = key[:20]
        try:
            raw = await self._hgetall(f"{STATE_KEY}{key_short}")
            if raw:
                return KeyState(
                    key=key_short,
                    status=raw.get(b"status", raw.get("status", "UNKNOWN")).decode() if isinstance(raw.get(b"status", raw.get("status", "UNKNOWN")), bytes) else raw.get("status", "UNKNOWN"),
                    available_credits=int(raw.get(b"available_credits", raw.get("available_credits", DEFAULT_CREDITS))),
                    estimated_credits_remaining=int(raw.get(b"estimated_credits_remaining", raw.get("estimated_credits_remaining", DEFAULT_CREDITS))),
                    reset_date=reset_date,
                    last_success=float(raw.get(b"last_success", 0)) if float(raw.get(b"last_success", 0)) > 0 else None,
                    last_failure=float(raw.get(b"last_failure", 0)) if float(raw.get(b"last_failure", 0)) > 0 else None,
                    consecutive_failures=int(raw.get(b"consecutive_failures", raw.get("consecutive_failures", 0))),
                    suspect_failures=int(raw.get(b"suspect_failures", raw.get("suspect_failures", 0))),
                    average_cost=float(raw.get(b"average_cost", raw.get("average_cost", DEFAULT_AVG_COST))),
                    requests_made=int(raw.get(b"requests_made", raw.get("requests_made", 0))),
                    last_detected_reset=raw.get(b"last_detected_reset", raw.get("last_detected_reset")),
                    next_estimated_reset=reset_date,
                    draining=raw.get(b"draining", raw.get("draining", "false")) in ("true", "True", True),
                    success_rate=float(raw.get(b"success_rate", raw.get("success_rate", 1.0))),
                )
        except Exception as e:
            logger.warning("state_load_failed", key=key_short, error=str(e))

        cache_state = self._emergency.get(key_short)
        if cache_state:
            return cache_state

        return KeyState(key=key_short, reset_date=reset_date, next_estimated_reset=reset_date)

    async def _save_state(self, state: KeyState) -> None:
        key_short = state.key
        try:
            mapping = {
                "status": state.status,
                "available_credits": str(state.available_credits),
                "estimated_credits_remaining": str(state.estimated_credits_remaining),
                "consecutive_failures": str(state.consecutive_failures),
                "suspect_failures": str(state.suspect_failures),
                "average_cost": str(state.average_cost),
                "requests_made": str(state.requests_made),
                "draining": str(state.draining),
                "success_rate": str(round(state.success_rate, 4)),
            }
            if state.last_success:
                mapping["last_success"] = str(state.last_success)
            if state.last_failure:
                mapping["last_failure"] = str(state.last_failure)
            if state.cooldown_until:
                mapping["cooldown_until"] = str(state.cooldown_until)
            if state.last_detected_reset:
                mapping["last_detected_reset"] = state.last_detected_reset
            if state.next_estimated_reset:
                mapping["next_estimated_reset"] = state.next_estimated_reset
            if state.suspect_window_start:
                mapping["suspect_window_start"] = str(state.suspect_window_start)
            if state.projected_hours_left is not None:
                mapping["projected_hours_left"] = str(round(state.projected_hours_left, 2))

            await self._hset(f"{STATE_KEY}{key_short}", mapping, expire=86400 * 31)
            self._emergency.set(state)
        except Exception as e:
            logger.warning("state_save_failed", key=key_short, error=str(e))

    async def _compute_predictions(self, state: KeyState) -> None:
        try:
            now = time.time()
            state.credits_burn_history = [x for x in state.credits_burn_history if now - x[0] < 3600]
            if state.credits_burn_history:
                burn_total = sum(c for _, c in state.credits_burn_history)
                credits_burn_rate = burn_total / max(1, len(state.credits_burn_history))
                if credits_burn_rate > 0:
                    state.projected_hours_left = state.estimated_credits_remaining / (credits_burn_rate * 60)
                    state.draining = state.projected_hours_left < DRAINING_THRESHOLD_HOURS
                else:
                    state.projected_hours_left = None
                    state.draining = False
            else:
                state.projected_hours_left = None
                state.draining = False
        except Exception:
            pass

    async def select_best_key(self, available_keys: list[str]) -> str | None:
        if not available_keys:
            return None
        candidates: list[tuple[float, str]] = []
        for key in available_keys:
            key_short = key[:20]
            state = self._local_states.get(key_short) or await self._load_state(key, None)
            if not state.is_available:
                continue
            w = state.weight
            if w > 0:
                candidates.append((w, key))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def record_success(self, key: str, cost: int, remaining: int, remaining_project: int) -> None:
        key_short = key[:20]
        state = self._local_states.get(key_short)
        if not state:
            return
        state.status = "ACTIVE"
        state.last_success = time.time()
        state.consecutive_failures = 0
        state.suspect_failures = 0
        state.suspect_window_start = None
        state.cooldown_until = None
        state.requests_made += 1
        state.available_credits = max(0, remaining)
        state.estimated_credits_remaining = max(0, remaining)
        state.credits_burn_history.append((time.time(), cost))

        total = state.consecutive_failures + max(0, state.requests_made - 5)
        state.success_rate = state.requests_made / (state.requests_made + total) if (state.requests_made + total) > 0 else 1.0

        cost_stats = await self._estimator.get_stats(key_short)
        state.average_cost = cost_stats["avg"]

        await self._estimator.record_cost(key_short, cost)
        await self._compute_predictions(state)
        await self._save_state(state)

    async def record_failure(self, key: str, status_code: int, error: str | None = None) -> None:
        key_short = key[:20]
        state = self._local_states.get(key_short)
        if not state:
            return
        state.last_failure = time.time()
        state.consecutive_failures += 1

        now = time.time()

        if status_code == 401:
            state.status = "DISABLED"
            state.cooldown_until = now + 86400 * 31
            logger.warning("key_disabled_auth_failure", key=key_short)

        elif status_code == 429:
            remaining = state.estimated_credits_remaining
            if remaining <= 0 or (error and "quota" in error.lower()):
                state.status = "EXHAUSTED"
                state.cooldown_until = now + EXHAUSTED_COOLDOWN
                logger.warning("key_exhausted", key=key_short)
            else:
                state.status = "COOLDOWN"
                state.cooldown_until = now + COOLDOWN_SECONDS
                logger.warning("key_rate_limited", key=key_short)

        else:
            if state.suspect_window_start is None or (now - state.suspect_window_start) > SUSPECT_WINDOW:
                state.suspect_window_start = now
                state.suspect_failures = 1
            else:
                state.suspect_failures += 1

            if state.suspect_failures >= COOLDOWN_AFTER_SUSPECT_FAILURES:
                state.status = "COOLDOWN"
                state.cooldown_until = now + COOLDOWN_SECONDS * (2 ** min(state.consecutive_failures, 5))
                state.suspect_failures = 0
                state.suspect_window_start = None
                logger.warning("key_cooldown_after_suspect", key=key_short, failures=state.consecutive_failures)
            elif state.suspect_failures >= MAX_SUSPECT_FAILURES:
                state.status = "SUSPECT"
                logger.warning("key_suspect", key=key_short, failures=state.suspect_failures)
            elif state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                state.status = "COOLDOWN"
                state.cooldown_until = now + COOLDOWN_SECONDS * (2 ** min(state.consecutive_failures, 5))
                logger.warning("key_consecutive_failures", key=key_short, count=state.consecutive_failures)

        total = state.consecutive_failures + max(0, state.requests_made - 5)
        state.success_rate = state.requests_made / (state.requests_made + total) if (state.requests_made + total) > 0 else 0.0

        await self._save_state(state)

    async def reserve_key(self, key: str) -> bool:
        key_short = key[:20]
        lock_name = f"{RESERVATION_KEY}{key_short}"
        try:
            acquired = await self._set(lock_name, WORKER_ID, nx=True, ex=RESERVATION_TTL)
            return acquired
        except Exception:
            return False

    async def renew_lease(self, key: str) -> bool:
        key_short = key[:20]
        lock_name = f"{RESERVATION_KEY}{key_short}"
        try:
            owner = await self._get(lock_name)
            if owner and (owner.decode() if isinstance(owner, bytes) else owner) == WORKER_ID:
                await self._redis.expire(lock_name, RESERVATION_TTL)
                return True
            return False
        except Exception:
            return False

    async def release_key(self, key: str) -> None:
        key_short = key[:20]
        lock_name = f"{RESERVATION_KEY}{key_short}"
        try:
            owner = await self._get(lock_name)
            if owner and (owner.decode() if isinstance(owner, bytes) else owner) == WORKER_ID:
                await self._delete(lock_name)
        except Exception:
            pass

    async def get_metrics(self) -> dict[str, Any]:
        try:
            raw = await self._hgetall(METRICS_KEY)
            if raw:
                return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in raw.items()}
        except Exception:
            pass
        return {}

    async def update_metrics(self, states: list[KeyState]) -> None:
        active = sum(1 for s in states if s.status == "ACTIVE" and s.is_available)
        suspect = sum(1 for s in states if s.status == "SUSPECT")
        draining = sum(1 for s in states if s.status == "DRAINING" or s.draining)
        cooldown = sum(1 for s in states if s.status == "COOLDOWN")
        exhausted = sum(1 for s in states if s.status == "EXHAUSTED")
        disabled = sum(1 for s in states if s.status == "DISABLED")
        unknown = sum(1 for s in states if s.status == "UNKNOWN")
        total_credits = sum(s.estimated_credits_remaining for s in states)
        total_requests = sum(s.requests_made for s in states)
        avg_cost = statistics.mean([s.average_cost for s in states if s.average_cost > 0]) if any(s.average_cost > 0 for s in states) else DEFAULT_AVG_COST
        estimated_scrapes = int(total_credits / avg_cost) if avg_cost > 0 else 0
        avg_success_rate = statistics.mean([s.success_rate for s in states]) if states else 0.0

        estimated_hours = None
        burn_rates = [s.estimated_credits_remaining / max(0.01, s.projected_hours_left) for s in states if s.projected_hours_left and s.projected_hours_left > 0]
        if burn_rates:
            avg_burn = statistics.mean(burn_rates) if burn_rates else 0
            if avg_burn > 0:
                estimated_hours = str(round(total_credits / avg_burn, 1))

        metrics = {
            "active_keys": str(active),
            "suspect_keys": str(suspect),
            "draining_keys": str(draining),
            "cooldown_keys": str(cooldown),
            "exhausted_keys": str(exhausted),
            "disabled_keys": str(disabled),
            "unknown_keys": str(unknown),
            "total_keys": str(len(states)),
            "total_credits_remaining": str(total_credits),
            "total_requests_made": str(total_requests),
            "average_cost_per_scrape": str(round(avg_cost, 1)),
            "estimated_scrapes_remaining": str(estimated_scrapes),
            "estimated_hours_remaining": estimated_hours or "unknown",
            "average_success_rate": str(round(avg_success_rate, 4)),
            "last_updated": str(time.time()),
            "dead_keys_count": str(disabled + exhausted),
            "emergency_cache_active": str(self._emergency.is_active),
        }
        try:
            await self._hset(METRICS_KEY, mapping=metrics, expire=86400 * 7)
        except Exception:
            pass


class RecoveryScheduler:
    """Checks for key recovery every 6 hours (general) and daily (monthly resets)."""

    def __init__(self, redis_conn: Any, state_manager: KeyStateManager) -> None:
        self._redis = redis_conn
        self._manager = state_manager
        self._last_recovery_check: float = 0
        self._last_monthly_check: float = 0

    async def run_recovery_cycle(self, keys: list[str], reset_dates: dict[str, str]) -> list[str]:
        now = time.time()
        revived: list[str] = []
        states = await self._manager.load_all_states(keys, reset_dates)

        for state in states:
            if state.status in ("COOLDOWN",):
                if state.cooldown_until and now >= state.cooldown_until:
                    state.status = "UNKNOWN"
                    state.cooldown_until = None
                    state.consecutive_failures = 0
                    state.suspect_failures = 0
                    await self._manager._save_state(state)
                    revived.append(state.key)
                    logger.info("key_recovered_from_cooldown", key=state.key)

            elif state.status in ("EXHAUSTED", "DISABLED"):
                if now >= (state.cooldown_until or 0):
                    reset_date = state.reset_date or reset_dates.get(state.key)
                    if reset_date:
                        try:
                            rd = datetime.strptime(reset_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) >= rd:
                                healthy = await self.health_check_key(
                                    next((k for k in keys if k[:20] == state.key), f"scp-live-{state.key}")
                                )
                                if healthy:
                                    remaining = state.estimated_credits_remaining
                                    if remaining > MIN_RESTORE_THRESHOLD:
                                        state.status = "ACTIVE"
                                        state.cooldown_until = None
                                        state.consecutive_failures = 0
                                        state.suspect_failures = 0
                                        state.last_detected_reset = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                                        state.next_estimated_reset = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
                                        await self._manager._save_state(state)
                                        revived.append(state.key)
                                        logger.info("key_recovered_after_reset", key=state.key, reset_date=reset_date)
                                    else:
                                        state.next_estimated_reset = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
                                        await self._manager._save_state(state)
                                        logger.info("key_reset_approaching_but_credits_low",
                                                     key=state.key, remaining=remaining, min_threshold=MIN_RESTORE_THRESHOLD)
                                else:
                                    state.next_estimated_reset = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
                                    await self._manager._save_state(state)
                                    logger.info("key_reset_health_check_failed", key=state.key)
                        except (ValueError, TypeError):
                            pass

            elif state.status == "SUSPECT":
                if now >= (state.suspect_window_start or 0) + SUSPECT_WINDOW:
                    if state.consecutive_failures == 0:
                        state.status = "ACTIVE"
                    else:
                        state.status = "COOLDOWN"
                    state.suspect_window_start = None
                    state.suspect_failures = 0
                    await self._manager._save_state(state)
                    revived.append(state.key)
                    logger.info("key_recovered_from_suspect", key=state.key)

            elif state.status == "UNKNOWN":
                state.status = "ACTIVE"
                await self._manager._save_state(state)
                revived.append(state.key)
                logger.info("key_recovered_from_unknown", key=state.key)

        if revived:
            await self._manager.update_metrics(states)

        self._last_recovery_check = now
        return revived

    async def health_check_key(self, key: str) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.scrapfly.io/account?key={key}",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    remaining = data.get("subscription", {}).get("usage", {}).get("scrape", {}).get("remaining", 0)
                    key_short = key[:20]
                    state = self._manager._local_states.get(key_short)
                    if state:
                        state.estimated_credits_remaining = max(0, remaining)
                        state.status = "ACTIVE"
                        await self._manager._save_state(state)
                    return True
        except Exception as e:
            logger.warning("health_check_failed", key=key[:20], error=str(e))
        return False
