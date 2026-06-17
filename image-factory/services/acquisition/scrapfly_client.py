from __future__ import annotations

import random
from typing import Any

import httpx

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

SCRAPFLY_BASE = "https://api.scrapfly.io/scrape"


class ScrapflyClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._redis = None
        self._session = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

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

    async def _track_usage(self, key: str, cost: int, remaining: int, remaining_project: int):
        try:
            r = await self._get_redis()
            key_short = key[:20]
            await r.hincrby("scrapfly:usage", f"{key_short}:cost", cost)
            await r.hset("scrapfly:usage", f"{key_short}:remaining", remaining)
            await r.hincrby("scrapfly:usage", "total_cost", cost)
            if remaining_project > 0:
                await r.set("scrapfly:remaining_project", remaining_project)
        except Exception as e:
            logger.warning("scrapfly_track_failed", error=str(e))

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        return self._client

    async def fetch_page(self, url: str, render_js: bool = False) -> str | None:
        if not settings.scrapfly_enabled:
            return None
        keys = await self._get_keys()
        if not keys:
            logger.warning("scrapfly_no_keys_configured")
            return None
        keys = list(keys)
        random.shuffle(keys)
        for key in keys:
            try:
                client = await self._get_client()
                params: dict[str, Any] = {
                    "key": key,
                    "url": url,
                    "asp": "true",
                }
                if render_js:
                    params["render_js"] = "true"

                resp = await client.get(SCRAPFLY_BASE, params=params)

                cost = int(resp.headers.get("x-scrapfly-api-cost", 0))
                remaining = int(resp.headers.get("x-scrapfly-remaining-api-credit", 0))
                remaining_project = int(resp.headers.get("x-scrapfly-project-remaining-api-credit", 0))
                await self._track_usage(key, cost, remaining, remaining_project)

                data = resp.json()

                if resp.status_code == 429:
                    logger.warning("scrapfly_rate_limited", key=key[:20])
                    continue

                if resp.status_code != 200:
                    error = data.get("error", data.get("message", str(resp.status_code)))
                    logger.warning("scrapfly_error", key=key[:20], error=error)
                    continue

                result = data.get("result", {})
                content = result.get("content")
                if content:
                    logger.info("scrapfly_success", url=url, js=render_js, cost=cost)
                    return content

                logger.warning("scrapfly_no_content", url=url)
            except Exception as e:
                logger.warning("scrapfly_exception", key=key[:20], error=str(e))
                continue
        return None

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
