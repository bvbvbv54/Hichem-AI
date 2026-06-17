from __future__ import annotations

import asyncio
import time
import random
from typing import Any

import httpx

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
]

TEST_URLS = [
    "http://example.com",
    "https://www.google.com",
]


class ProxyManager:
    def __init__(self) -> None:
        self._pool: list[dict[str, Any]] = []
        self._last_refresh: float = 0.0
        self._refresh_interval: float = settings.proxy_refresh_interval
        self._max_latency: float = settings.proxy_max_latency
        self._lock = asyncio.Lock()
        self._test_client: httpx.AsyncClient | None = None
        self._fetch_client: httpx.AsyncClient | None = None

    async def _get_fetch_client(self) -> httpx.AsyncClient:
        if self._fetch_client is None:
            self._fetch_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._fetch_client

    async def _get_test_client(self) -> httpx.AsyncClient:
        if self._test_client is None:
            self._test_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._max_latency + 5.0),
                follow_redirects=False,
            )
        return self._test_client

    async def _fetch_proxy_list(self, url: str) -> list[str]:
        try:
            client = await self._get_fetch_client()
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            proxies = []
            for line in resp.text.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                if len(parts) == 2:
                    ip, port = parts[0].strip(), parts[1].strip()
                    if ip and port.isdigit():
                        proxies.append(f"{ip}:{port}")
            return proxies
        except Exception as e:
            logger.warning("proxy_source_failed", url=url, error=str(e))
            return []

    async def _test_proxy(self, proxy: str) -> float | None:
        for test_url in TEST_URLS:
            try:
                client = await self._get_test_client()
                start = time.monotonic()
                resp = await client.get(test_url, proxy=f"http://{proxy}")
                elapsed = time.monotonic() - start
                if resp.status_code in (200, 301, 302, 403):
                    return elapsed
            except Exception:
                continue
        return None

    async def refresh_pool(self) -> None:
        now = time.time()
        if now - self._last_refresh < self._refresh_interval:
            return

        async with self._lock:
            if now - self._last_refresh < self._refresh_interval:
                return

            logger.info("proxy_refresh_started")
            all_raw: list[str] = []
            for source in PROXY_SOURCES:
                raw = await self._fetch_proxy_list(source)
                logger.info("proxy_source_result", url=source, count=len(raw))
                all_raw.extend(raw)

            if not all_raw:
                logger.warning("proxy_no_sources_returned_proxies")
                self._last_refresh = now
                return

            all_raw = list(set(all_raw))
            random.shuffle(all_raw)

            sample = all_raw[:20]
            logger.info("proxy_testing", count=len(sample))

            tested = await asyncio.gather(*[self._test_proxy(p) for p in sample], return_exceptions=True)

            good: list[dict[str, Any]] = []
            for proxy, latency in zip(sample, tested):
                if isinstance(latency, (int, float)) and latency < self._max_latency:
                    good.append({"proxy": f"http://{proxy}", "latency": latency, "last_used": 0.0})

            good.sort(key=lambda x: x["latency"])
            self._pool = good
            self._last_refresh = now
            logger.info("proxy_pool_refreshed", total=len(self._pool))

    async def get_proxy(self) -> str | None:
        if not settings.proxy_enabled:
            return None
        if not self._pool:
            await self.refresh_pool()
        if not self._pool:
            return None

        candidates = [p for p in self._pool if time.time() - p["last_used"] > 10.0]
        if not candidates:
            candidates = self._pool

        entry = random.choice(candidates)
        entry["last_used"] = time.time()
        return entry["proxy"]

    async def close(self) -> None:
        if self._test_client:
            await self._test_client.aclose()
            self._test_client = None
        if self._fetch_client:
            await self._fetch_client.aclose()
            self._fetch_client = None


_instance: ProxyManager | None = None


def get_proxy_manager() -> ProxyManager:
    global _instance
    if _instance is None:
        _instance = ProxyManager()
    return _instance
