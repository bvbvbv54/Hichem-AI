from __future__ import annotations

from typing import Any

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


class BrowserClient:
    def __init__(self) -> None:
        self._page: Any = None
        self._browser: Any = None

    async def fetch_page(self, url: str) -> str | None:
        if not settings.use_browser_fallback:
            logger.info("browser_fallback_disabled")
            return None
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright_not_installed")
            return None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=settings.playwright_headless)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                await browser.close()
                logger.info("browser_fetch_success", url=url, html_length=len(html))
                return html
        except Exception as exc:
            logger.error("browser_fetch_failed", url=url, error=str(exc))
            return None

    async def close(self) -> None:
        pass
