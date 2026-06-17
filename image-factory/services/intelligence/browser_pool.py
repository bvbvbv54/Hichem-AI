from __future__ import annotations

import asyncio
import random
from collections import OrderedDict
from datetime import datetime
from typing import Any

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

_MAX_POOL_SIZE = 5
_BROWSER_IDLE_TIMEOUT = 300
_CONTEXT_MAX_AGE = 1800
_CONTEXT_MAX_REQUESTS = 50


class BrowserPool:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self.emitter = emitter or EventEmitter()
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._context_usage: dict[str, int] = {}
        self._context_created: dict[str, float] = {}
        self._context_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_browser(self) -> Any:
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.warning("playwright_not_installed")
                return None
            try:
                self._playwright = await async_playwright().__aenter__()
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.playwright_headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                        "--no-zygote",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                self._initialized = True
                logger.info("browser_pool_launched")
            except Exception as exc:
                logger.error("browser_pool_launch_failed", error=str(exc))
                return None
        return self._browser

    async def acquire_context(self, marketplace: str = "", session_id: str = "") -> Any | None:
        async with self._context_lock:
            await self._evict_stale_contexts()

            context_id = None
            for cid in list(self._contexts.keys()):
                usage = self._context_usage.get(cid, 0)
                age = datetime.utcnow().timestamp() - self._context_created.get(cid, 0)
                if age < _CONTEXT_MAX_AGE and usage < _CONTEXT_MAX_REQUESTS:
                    context_id = cid
                    break

            if context_id:
                context_info = self._contexts.pop(context_id)
                self._contexts[context_id] = context_info
                context = context_info["context"]
                self._context_usage[context_id] += 1
                logger.info("browser_context_reused", context_id=context_id, usage=self._context_usage[context_id])
                await self.emitter.emit(IntelligenceEventType.BROWSER_CONTEXT_REUSED, marketplace or "unknown", {
                    "context_id": context_id,
                    "usage_count": self._context_usage[context_id],
                    "session_id": session_id,
                })
                return context

            return await self._create_context(marketplace, session_id)

    async def _create_context(self, marketplace: str = "", session_id: str = "") -> Any | None:
        browser = await self._ensure_browser()
        if not browser:
            return None

        if len(self._contexts) >= _MAX_POOL_SIZE:
            oldest_id, oldest_info = self._contexts.popitem(last=False)
            try:
                await oldest_info["context"].close()
            except Exception:
                pass
            logger.info("browser_context_evicted", context_id=oldest_id)

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
        ]

        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport=random.choice(viewports),
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            ignore_https_errors=True,
            bypass_csp=True,
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        import uuid
        context_id = str(uuid.uuid4())
        self._contexts[context_id] = {"context": context, "marketplace": marketplace, "session_id": session_id}
        self._context_usage[context_id] = 1
        self._context_created[context_id] = datetime.utcnow().timestamp()

        await self.emitter.emit(IntelligenceEventType.BROWSER_CONTEXT_CREATED, marketplace or "unknown", {
            "context_id": context_id,
            "session_id": session_id,
            "pool_size": len(self._contexts),
        })
        logger.info("browser_context_created", context_id=context_id, pool_size=len(self._contexts))
        return context

    async def release_context(self, context: Any) -> None:
        async with self._context_lock:
            for cid, info in list(self._contexts.items()):
                if info["context"] == context:
                    usage = self._context_usage.get(cid, 0)
                    age = datetime.utcnow().timestamp() - self._context_created.get(cid, 0)
                    if usage >= _CONTEXT_MAX_REQUESTS or age >= _CONTEXT_MAX_AGE:
                        try:
                            await context.close()
                        except Exception:
                            pass
                        del self._contexts[cid]
                        del self._context_usage[cid]
                        del self._context_created[cid]
                        logger.info("browser_context_closed_after_use", context_id=cid, usage=usage)
                    return

    async def _evict_stale_contexts(self) -> None:
        now = datetime.utcnow().timestamp()
        stale_ids = []
        for cid, info in list(self._contexts.items()):
            age = now - self._context_created.get(cid, 0)
            usage = self._context_usage.get(cid, 0)
            if age > _BROWSER_IDLE_TIMEOUT or usage >= _CONTEXT_MAX_REQUESTS:
                stale_ids.append(cid)
        for cid in stale_ids:
            if cid in self._contexts:
                try:
                    await self._contexts[cid]["context"].close()
                except Exception:
                    pass
                del self._contexts[cid]
                if cid in self._context_usage:
                    del self._context_usage[cid]
                if cid in self._context_created:
                    del self._context_created[cid]
                logger.info("browser_context_evicted_stale", context_id=cid)

    async def close(self) -> None:
        for cid in list(self._contexts.keys()):
            try:
                await self._contexts[cid]["context"].close()
            except Exception:
                pass
        self._contexts.clear()
        self._context_usage.clear()
        self._context_created.clear()
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
                self._playwright = None
        except Exception as exc:
            logger.warning("browser_pool_close_error", error=str(exc))
        self._initialized = False
        logger.info("browser_pool_closed")
