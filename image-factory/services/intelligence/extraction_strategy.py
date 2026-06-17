from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

from configs.logging import get_logger
from services.intelligence.models import (
    ExtractionMethod,
    ExtractionAttempt,
    IntelligenceEventType,
)
from services.intelligence.event_emitter import EventEmitter
from services.intelligence.profile_manager import MarketplaceProfileManager
from services.intelligence.request_engine import AdaptiveRequestEngine

logger = get_logger(__name__)

STRATEGY_STATS_PREFIX = "intel:strategy:"

STRATEGY_ORDER = [
    ExtractionMethod.JSON_LD,
    ExtractionMethod.EMBEDDED_JSON,
    ExtractionMethod.INTERNAL_API,
    ExtractionMethod.STATIC_HTML,
    ExtractionMethod.BROWSER_AUTOMATION,
    ExtractionMethod.AI_EXTRACTION,
]


class ExtractionStrategyHierarchy:
    def __init__(
        self,
        profile_manager: MarketplaceProfileManager | None = None,
        request_engine: AdaptiveRequestEngine | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.profile_manager = profile_manager or MarketplaceProfileManager()
        self.request_engine = request_engine or AdaptiveRequestEngine()
        self.emitter = emitter or EventEmitter()
        self._strategy_success: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._extractors: dict[ExtractionMethod, Callable | None] = {}

    def register_extractor(self, method: ExtractionMethod, extractor: Callable) -> None:
        self._extractors[method] = extractor

    async def extract(self, url: str, html: str | None = None, marketplace: str = "") -> tuple[ExtractionMethod | None, dict[str, Any] | None]:
        domain = marketplace or urlparse(url).netloc.replace("www.", "")
        profile = await self.profile_manager.get_profile(domain)

        preferred = profile.preferred_extraction_method if profile else ""
        strategy_order = list(STRATEGY_ORDER)

        if preferred:
            preferred_method = ExtractionMethod(preferred)
            strategy_order.remove(preferred_method)
            strategy_order.insert(0, preferred_method)

        for method in strategy_order:
            extractor = self._extractors.get(method)
            if not extractor:
                continue
            start = time.monotonic()
            try:
                result = await extractor(url, html)
                duration_ms = (time.monotonic() - start) * 1000
                if result:
                    attempt = ExtractionAttempt(
                        method=method,
                        success=True,
                        duration_ms=duration_ms,
                        marketplace=domain,
                        url=url,
                    )
                    await self._record_attempt(attempt, domain)
                    await self.emitter.emit(IntelligenceEventType.STRATEGY_SELECTED, domain, {
                        "method": method.value,
                        "duration_ms": duration_ms,
                        "url": url,
                    })
                    await self._update_profile_preference(domain, method)
                    logger.info("extraction_success", method=method.value, url=url)
                    return method, result
                attempt = ExtractionAttempt(
                    method=method,
                    success=False,
                    duration_ms=duration_ms,
                    marketplace=domain,
                    url=url,
                    error="Extractor returned no result",
                )
                await self._record_attempt(attempt, domain)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                attempt = ExtractionAttempt(
                    method=method,
                    success=False,
                    duration_ms=duration_ms,
                    marketplace=domain,
                    url=url,
                    error=str(exc),
                )
                await self._record_attempt(attempt, domain)
                await self.emitter.emit(IntelligenceEventType.STRATEGY_FAILED, domain, {
                    "method": method.value,
                    "error": str(exc),
                    "url": url,
                })
                logger.warning("extraction_failed", method=method.value, url=url, error=str(exc))
        return None, None

    async def _record_attempt(self, attempt: ExtractionAttempt, domain: str) -> None:
        import redis.asyncio as aioredis
        from configs.settings import settings
        redis_conn = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            method_key = f"{STRATEGY_STATS_PREFIX}{domain}:{attempt.method.value}"
            pipe = redis_conn.pipeline()
            pipe.hincrby(method_key, "total", 1)
            if attempt.success:
                pipe.hincrby(method_key, "success", 1)
            else:
                pipe.hincrby(method_key, "failure", 1)
            pipe.hincrbyfloat(method_key, "total_duration", attempt.duration_ms)
            pipe.expire(method_key, 86400 * 30)
            await pipe.execute()
        finally:
            await redis_conn.aclose()

    async def get_strategy_stats(self, domain: str) -> dict[str, Any]:
        import redis.asyncio as aioredis
        from configs.settings import settings
        redis_conn = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            stats: dict[str, Any] = {}
            for method in ExtractionMethod:
                method_key = f"{STRATEGY_STATS_PREFIX}{domain}:{method.value}"
                data = await redis_conn.hgetall(method_key)
                if data:
                    total = int(data.get(b"total", data.get("total", 0)))
                    success = int(data.get(b"success", data.get("success", 0)))
                    failure = int(data.get(b"failure", data.get("failure", 0)))
                    total_duration = float(data.get(b"total_duration", data.get("total_duration", 0.0)))
                    stats[method.value] = {
                        "total": total,
                        "success": success,
                        "failure": failure,
                        "success_rate": round(success / total, 4) if total > 0 else 0.0,
                        "avg_duration_ms": round(total_duration / total, 2) if total > 0 else 0.0,
                    }
            return stats
        finally:
            await redis_conn.aclose()

    async def _update_profile_preference(self, domain: str, successful_method: ExtractionMethod) -> None:
        stats = await self.get_strategy_stats(domain)
        if stats:
            best_method = max(stats, key=lambda m: stats[m].get("success_rate", 0))
            profile = await self.profile_manager.get_profile(domain)
            if profile and best_method != profile.preferred_extraction_method:
                profile.preferred_extraction_method = best_method
                profile.extraction_success_rates = {m: s["success_rate"] for m, s in stats.items()}
                profile.last_updated = datetime.utcnow().isoformat()
                await self.profile_manager.save_profile(domain, profile)
