from __future__ import annotations

import time
from urllib.parse import urlparse, urlunparse
from typing import Any

import httpx
import redis.asyncio as redis_async
from urllib.robotparser import RobotFileParser

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.models import FailureType

logger = get_logger(__name__)

_USER_AGENT = "ImageFactoryBot/1.0"


class RobotsChecker:
    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None
        self._cache: dict[str, tuple[RobotFileParser, float]] = {}
        self._crawl_delays: dict[str, float] = {}

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def is_allowed(self, url: str) -> tuple[bool, FailureType | None]:
        parsed = urlparse(url)
        domain = parsed.netloc
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        rp = await self._fetch_robots(robots_url, domain)
        if rp is None:
            return True, None
        allowed = rp.can_fetch(_USER_AGENT, url)
        if not allowed:
            logger.info("robots_disallowed", url=url, domain=domain)
            return False, FailureType.ROBOTS_DISALLOWED
        delay = rp.crawl_delay(_USER_AGENT)
        if delay is not None and delay > 0:
            self._crawl_delays[domain] = float(delay)
        return True, None

    def get_crawl_delay(self, domain: str) -> float:
        return self._crawl_delays.get(domain, 0.0)

    async def _fetch_robots(self, robots_url: str, domain: str) -> RobotFileParser | None:
        now = time.time()
        cached = self._cache.get(domain)
        if cached and now - cached[1] < 86400:
            return cached[0]
        try:
            rp = RobotFileParser()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(robots_url, headers={"User-Agent": _USER_AGENT})
                if response.status_code in (200, 404):
                    raw = response.text if response.status_code == 200 else ""
                    rp.parse(raw.splitlines() if raw else [])
                    self._cache[domain] = (rp, now)
                    return rp
                return None
        except Exception as exc:
            logger.warning("robots_fetch_failed", domain=domain, error=str(exc))
            return None

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
