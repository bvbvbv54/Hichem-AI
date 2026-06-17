from __future__ import annotations

import asyncio
import random
from typing import Any

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

_LOCALES = ["en-US", "en-GB", "en"]


class BrowserClient:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context_counter = 0
        self._lock = asyncio.Lock()

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
                logger.info("browser_launched")
            except Exception as exc:
                logger.error("browser_launch_failed", error=str(exc))
                return None
        return self._browser

    async def _create_context(self) -> Any | None:
        browser = await self._ensure_browser()
        if not browser:
            return None
        ua = random.choice(_USER_AGENTS)
        vp = random.choice(_VIEWPORTS)
        locale = random.choice(_LOCALES)
        context = await browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale=locale,
            timezone_id="America/New_York",
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            device_scale_factor=1,
            has_touch=False,
            ignore_https_errors=True,
            bypass_csp=True,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            },
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)
        return context

    async def fetch_page(self, url: str, timeout: int = 60000) -> str | None:
        async with self._lock:
            context = await self._create_context()
            if not context:
                return None
            page = None
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await page.wait_for_timeout(random.randint(2000, 5000))
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(random.randint(1000, 2000))
                await page.evaluate("window.scrollTo(0, 0)")
                html = await page.content()
                logger.info("browser_fetch_success", url=url, html_length=len(html))
                return html
            except Exception as exc:
                logger.error("browser_fetch_failed", url=url, error=str(exc))
                return None
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                try:
                    await context.close()
                except Exception:
                    pass

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
                self._playwright = None
            logger.info("browser_closed")
        except Exception as exc:
            logger.warning("browser_close_error", error=str(exc))
