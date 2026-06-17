from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

_USER_AGENTS: list[str] | None = None


def _load_user_agents() -> list[str]:
    global _USER_AGENTS
    if _USER_AGENTS is not None:
        return _USER_AGENTS
    ua_path = Path(__file__).parents[2] / "configs" / "user_agents.txt"
    if not ua_path.exists():
        _USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ]
        return _USER_AGENTS
    agents = [line.strip() for line in ua_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    _USER_AGENTS = agents if agents else [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ]
    return _USER_AGENTS


def _random_headers() -> dict[str, str]:
    ua = random.choice(_load_user_agents())
    chrome_version = "131"
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
    }


class HardenedHTTPClient:
    def __init__(self) -> None:
        from services.acquisition.proxy_manager import get_proxy_manager

        self.proxy_manager = get_proxy_manager()
        self.client = httpx.AsyncClient(
            headers=_random_headers(),
            timeout=httpx.Timeout(
                connect=settings.scraper_connect_timeout,
                read=settings.scraper_read_timeout,
                write=10.0,
                pool=10.0,
            ),
            follow_redirects=True,
            cookies=httpx.Cookies(),
        )
        self._cookies_per_domain: dict[str, dict[str, str]] = {}

    async def _wait_delay(self) -> None:
        if settings.request_delay_enabled:
            delay = random.uniform(settings.request_delay_min, settings.request_delay_max)
            logger.debug("request_delay", delay_seconds=round(delay, 2))
            await asyncio.sleep(delay)

    async def close(self) -> None:
        await self.client.aclose()
        await self.proxy_manager.close()

    def rotate_headers(self) -> None:
        self.client.headers.update(_random_headers())

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        await self._wait_delay()
        self.rotate_headers()
        proxy = await self.proxy_manager.get_proxy()
        domain = httpx.URL(url).host or ""
        domain_cookies = self._cookies_per_domain.get(domain, {})
        if domain_cookies:
            for key, value in domain_cookies.items():
                self.client.cookies.set(key, value, domain=domain)
        if proxy:
            kwargs["proxy"] = proxy
        response = await self.client.get(url, **kwargs)
        for cookie in self.client.cookies.jar:
            if cookie.domain and domain in cookie.domain:
                self._cookies_per_domain.setdefault(domain, {})[cookie.name] = cookie.value
        return response

    async def fetch_with_retry(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._retry_get(url, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=lambda attempt: 1.0 * (2 ** attempt) + random.uniform(0, 1)),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    )
    async def _retry_get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.get(url, **kwargs)
