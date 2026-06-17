from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import MarketplaceHealth, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

HEALTH_PREFIX = "intel:health:"
HEALTH_WINDOW = 3600
ALERT_THRESHOLD = 0.3

TIER_1_MARKETPLACES = ["1688.com", "taobao.com", "tmall.com", "alibaba.com", "aliexpress.com"]
TIER_2_MARKETPLACES = ["jd.com", "pinduoduo.com", "temu.com", "dhgate.com", "made-in-china.com"]
ALL_MARKETPLACES = TIER_1_MARKETPLACES + TIER_2_MARKETPLACES


class MarketplaceHealthMonitor:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self._redis: aioredis.Redis | None = None
        self.emitter = emitter or EventEmitter()
        self._local_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._local_durations: dict[str, list[float]] = defaultdict(list)

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def record_extraction(
        self,
        marketplace: str,
        success: bool,
        duration_ms: float,
        was_captcha: bool = False,
        was_blocked: bool = False,
    ) -> None:
        redis_conn = await self._get_redis()
        now = int(datetime.utcnow().timestamp())
        window_key = f"{now // HEALTH_WINDOW}"
        key_base = f"{HEALTH_PREFIX}{marketplace}:{window_key}"
        pipe = redis_conn.pipeline()
        total_key = f"{key_base}:total"
        success_key = f"{key_base}:success"
        failure_key = f"{key_base}:failure"
        captcha_key = f"{key_base}:captcha"
        blocked_key = f"{key_base}:blocked"
        duration_key = f"{key_base}:duration"
        pipe.incr(total_key)
        if success:
            pipe.incr(success_key)
        else:
            pipe.incr(failure_key)
        if was_captcha:
            pipe.incr(captcha_key)
        if was_blocked:
            pipe.incr(blocked_key)
        pipe.incrbyfloat(duration_key, duration_ms)
        pipe.expire(total_key, HEALTH_WINDOW + 120)
        pipe.expire(success_key, HEALTH_WINDOW + 120)
        pipe.expire(failure_key, HEALTH_WINDOW + 120)
        pipe.expire(captcha_key, HEALTH_WINDOW + 120)
        pipe.expire(blocked_key, HEALTH_WINDOW + 120)
        pipe.expire(duration_key, HEALTH_WINDOW + 120)
        await pipe.execute()
        self._local_counts[marketplace]["total"] += 1
        if success:
            self._local_counts[marketplace]["success"] += 1
        else:
            self._local_counts[marketplace]["failure"] += 1
        if was_captcha:
            self._local_counts[marketplace]["captcha"] += 1
        if was_blocked:
            self._local_counts[marketplace]["blocked"] += 1
        self._local_durations[marketplace].append(duration_ms)

        await self._check_alert(marketplace)

    async def _check_alert(self, marketplace: str) -> None:
        health = await self.get_current_health(marketplace)
        if health.total_requests >= 5 and health.success_rate < ALERT_THRESHOLD:
            await self.emitter.emit(IntelligenceEventType.HEALTH_ALERT, marketplace, {
                "success_rate": health.success_rate,
                "captcha_rate": health.captcha_rate,
                "total_requests": health.total_requests,
                "alert_threshold": ALERT_THRESHOLD,
            })

    async def get_current_health(self, marketplace: str) -> MarketplaceHealth:
        redis_conn = await self._get_redis()
        now = int(datetime.utcnow().timestamp())
        current_window = f"{now // HEALTH_WINDOW}"
        prev_window = f"{(now - HEALTH_WINDOW) // HEALTH_WINDOW}"
        keys = [f"{HEALTH_PREFIX}{marketplace}:{w}" for w in (current_window, prev_window)]
        total = 0
        success_count = 0
        failure_count = 0
        captcha_count = 0
        blocked_count = 0
        total_duration = 0.0
        for key in keys:
            vals = await redis_conn.mget(
                f"{key}:total",
                f"{key}:success",
                f"{key}:failure",
                f"{key}:captcha",
                f"{key}:blocked",
                f"{key}:duration",
            )
            for i, v in enumerate(vals):
                if v is None:
                    vals[i] = 0
                else:
                    try:
                        vals[i] = int(v) if i < 5 else float(v)
                    except (ValueError, TypeError):
                        vals[i] = 0
            total += int(vals[0])
            success_count += int(vals[1])
            failure_count += int(vals[2])
            captcha_count += int(vals[3])
            blocked_count += int(vals[4])
            total_duration += float(vals[5])
        total_reqs = total or 1
        period_end = datetime.utcnow().isoformat()
        period_start = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        return MarketplaceHealth(
            marketplace=marketplace,
            period_start=period_start,
            period_end=period_end,
            total_requests=total,
            success_count=success_count,
            failure_count=failure_count,
            captcha_count=captcha_count,
            blocked_count=blocked_count,
            avg_extraction_time_ms=round(total_duration / total_reqs, 2),
            success_rate=round(success_count / total_reqs, 4),
            captcha_rate=round(captcha_count / total_reqs, 4),
        )

    async def get_all_marketplace_health(self) -> list[MarketplaceHealth]:
        results: list[MarketplaceHealth] = []
        for mp in ALL_MARKETPLACES:
            health = await self.get_current_health(mp)
            results.append(health)
        return results

    async def get_historical_health(self, marketplace: str, hours: int = 24) -> list[MarketplaceHealth]:
        redis_conn = await self._get_redis()
        now = int(datetime.utcnow().timestamp())
        windows = hours * 3600 // HEALTH_WINDOW
        results: list[MarketplaceHealth] = []
        for i in range(windows):
            window_key = f"{(now - i * HEALTH_WINDOW) // HEALTH_WINDOW}"
            key = f"{HEALTH_PREFIX}{marketplace}:{window_key}"
            vals = await redis_conn.mget(
                f"{key}:total",
                f"{key}:success",
                f"{key}:failure",
                f"{key}:captcha",
                f"{key}:blocked",
                f"{key}:duration",
            )
            total = int(vals[0]) if vals[0] else 0
            if total == 0:
                continue
            success_count = int(vals[1]) if vals[1] else 0
            failure_count = int(vals[2]) if vals[2] else 0
            captcha_count = int(vals[3]) if vals[3] else 0
            blocked_count = int(vals[4]) if vals[4] else 0
            total_duration = float(vals[5]) if vals[5] else 0.0
            window_time = datetime.utcfromtimestamp(int(window_key) * HEALTH_WINDOW)
            results.append(MarketplaceHealth(
                marketplace=marketplace,
                period_start=window_time.isoformat(),
                period_end=(window_time + timedelta(seconds=HEALTH_WINDOW)).isoformat(),
                total_requests=total,
                success_count=success_count,
                failure_count=failure_count,
                captcha_count=captcha_count,
                blocked_count=blocked_count,
                avg_extraction_time_ms=round(total_duration / total, 2),
                success_rate=round(success_count / total, 4),
                captcha_rate=round(captcha_count / total, 4),
            ))
        return results

    async def get_trend_report(self) -> dict[str, Any]:
        all_health = await self.get_all_marketplace_health()
        best = max(all_health, key=lambda h: h.success_rate) if all_health else None
        worst = min(all_health, key=lambda h: h.success_rate) if all_health else None
        most_captcha = max(all_health, key=lambda h: h.captcha_rate) if all_health else None
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "marketplace_count": len(all_health),
            "best_performing": {"marketplace": best.marketplace, "success_rate": best.success_rate} if best else None,
            "worst_performing": {"marketplace": worst.marketplace, "success_rate": worst.success_rate} if worst else None,
            "most_captcha": {"marketplace": most_captcha.marketplace, "captcha_rate": most_captcha.captcha_rate} if most_captcha else None,
            "marketplaces": [h.to_dict() for h in all_health],
        }

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
