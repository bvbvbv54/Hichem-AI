from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
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
_CN_LOCALE = "zh-CN"
_CN_TIMEZONE = "Asia/Shanghai"
_CN_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]
_CN_DOMAINS = {"1688.com", "taobao.com", "tmall.com", "detail.1688.com"}

SESSION_DIR = Path(settings.storage_path) / "browser_sessions"


def _domain_config(url: str) -> dict:
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""
    for d in _CN_DOMAINS:
        if d in hostname:
            return {
                "locale": _CN_LOCALE,
                "timezone_id": _CN_TIMEZONE,
                "geolocation": {"latitude": 31.2304, "longitude": 121.4737},
                "user_agent": random.choice(_CN_USER_AGENTS),
                "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
                "languages_script": "zh-CN,zh,en",
            }
    return {
        "locale": random.choice(_LOCALES),
        "timezone_id": "America/New_York",
        "geolocation": {"latitude": 40.7128, "longitude": -74.0060},
        "user_agent": random.choice(_USER_AGENTS),
        "accept_language": "en-US,en;q=0.9",
        "languages_script": "en-US,en",
    }


def _deep_get(obj: Any, path: str, default: Any = None) -> Any:
    parts = path.split(".")
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return default
        if obj is None:
            return default
    return obj


class BrowserClient:
    def __init__(self) -> None:
        self._playwright_cm: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context_counter = 0
        self._lock = asyncio.Lock()

    # ── Session persistence helpers ─────────────────────────────────
    def _session_path(self, url: str) -> Path:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or "unknown"
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        return SESSION_DIR / f"{host.replace('.', '_')}_storage.json"

    async def _load_session(self, context: Any, url: str) -> None:
        try:
            path = self._session_path(url)
            if path.exists():
                storage = json.loads(path.read_text())
                await context.add_cookies(storage.get("cookies", []))
                logger.info("session_loaded", url=url, path=str(path))
        except Exception as e:
            logger.warning("session_load_failed", error=str(e))

    async def _save_session(self, context: Any, url: str) -> None:
        try:
            storage = await context.storage_state()
            path = self._session_path(url)
            path.write_text(json.dumps(storage, indent=2))
            logger.info("session_saved", url=url, path=str(path))
        except Exception as e:
            logger.warning("session_save_failed", error=str(e))

    # ── Proxy support ───────────────────────────────────────────────
    async def _get_proxy(self) -> str | None:
        try:
            from services.acquisition.proxy_manager import get_proxy_manager
            return await get_proxy_manager().get_proxy()
        except Exception:
            return None

    async def _ensure_browser(self) -> Any:
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.warning("playwright_not_installed")
                return None
            try:
                self._playwright_cm = async_playwright()
                self._playwright = await self._playwright_cm.__aenter__()
                proxy_url = await self._get_proxy() if settings.proxy_enabled else None
                launch_opts = dict(
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
                if proxy_url:
                    launch_opts["proxy"] = {"server": proxy_url}
                self._browser = await self._playwright.chromium.launch(**launch_opts)
                logger.info("browser_launched", proxy=bool(proxy_url))
            except Exception as exc:
                logger.error("browser_launch_failed", error=str(exc))
                return None
        return self._browser

    async def _create_context(self, url: str = "https://www.amazon.com") -> Any | None:
        browser = await self._ensure_browser()
        if not browser:
            return None
        cfg = _domain_config(url)
        vp = random.choice(_VIEWPORTS)
        context = await browser.new_context(
            user_agent=cfg["user_agent"],
            viewport=vp,
            locale=cfg["locale"],
            timezone_id=cfg["timezone_id"],
            permissions=["geolocation"],
            geolocation=cfg["geolocation"],
            device_scale_factor=1,
            has_touch=False,
            ignore_https_errors=True,
            bypass_csp=True,
            extra_http_headers={
                "Accept-Language": cfg["accept_language"],
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            },
        )
        # Restore previous session state (cookies, localStorage, etc.)
        await self._load_session(context, url)
        lang_script = cfg["languages_script"]
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
            Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3, 4, 5] }});
            Object.defineProperty(navigator, 'languages', {{ get: () => ['{lang_script}'] }});
            window.chrome = {{ runtime: {{}} }};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({{ state: Notification.permission }}) :
                originalQuery(parameters)
            );
        """)
        return context

    API_IMAGE_ENDPOINTS = {
        "api/oak/integration/render": ["goods.hd_thumb_url", "goods.galleryImgs", "hd_thumb_url"],
        "api/goods/detail": ["goodsImage", "goodsImgs", "goods.images", "data.images"],
        "detail/image/list": ["images", "data.images"],
        "api/images": ["images", "data.urls"],
        "product/detail": ["data.images", "result.images"],
    }

    async def _capture_api_images(self, page: Any) -> list[str]:
        captured: list[str] = []
        async def handle_response(response: Any) -> None:
            url = response.url
            for endpoint, fields in self.API_IMAGE_ENDPOINTS.items():
                if endpoint in url and response.ok:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            for field in fields:
                                val = _deep_get(data, field)
                                if isinstance(val, str) and val.startswith("http"):
                                    captured.append(val)
                                elif isinstance(val, list):
                                    for item in val:
                                        if isinstance(item, str) and item.startswith("http"):
                                            captured.append(item)
                                        elif isinstance(item, dict):
                                            for f in ("url", "src", "imageUrl", "imgUrl", "hd_url"):
                                                if item.get(f) and str(item[f]).startswith("http"):
                                                    captured.append(str(item[f]))
                    except Exception:
                        pass
        page.on("response", handle_response)
        return captured

    async def fetch_page(self, url: str, timeout: int = 90000) -> str | None:
        result = await self.fetch_page_with_api(url, timeout)
        return result[0] if result else None

    async def fetch_page_with_api(self, url: str, timeout: int = 120000) -> tuple[str | None, list[str]]:
        async with self._lock:
            for attempt in range(2):
                try:
                    context = await self._create_context(url)
                    if not context:
                        return None, []
                    page = None
                    try:
                        page = await context.new_page()
                        api_images = await self._capture_api_images(page)
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=timeout)
                        except Exception:
                            try:
                                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            except Exception:
                                pass
                        await page.wait_for_timeout(random.randint(3000, 6000))
                        for _ in range(3):
                            await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 3)")
                            await page.wait_for_timeout(1500)
                        scroll_y = 0
                        for _ in range(3):
                            scroll_y += min(800, int(await page.evaluate("document.body.scrollHeight")) // 3)
                            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                            await page.wait_for_timeout(2000)
                            await page.wait_for_timeout(random.randint(500, 1500))
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(1000)
                        html = await page.content()
                        logger.info("browser_fetch_success", url=url, html_length=len(html), api_images=len(api_images))
                        return html, api_images
                    except Exception as exc:
                        err_str = str(exc)
                        if attempt == 0 and any(x in err_str for x in ["Target page", "closed", "Connection"]):
                            logger.warning("browser_reset_on_closed", url=url)
                            self._browser = None
                            self._playwright = None
                            self._playwright_cm = None
                            continue
                        logger.error("browser_fetch_failed", url=url, error=str(exc))
                        return None, []
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
                except Exception as exc:
                    err_str = str(exc)
                    if attempt == 0 and any(x in err_str for x in ["Target page", "closed", "Connection"]):
                        self._browser = None
                        self._playwright = None
                        self._playwright_cm = None
                        continue
                    return None, []
            return None, []

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright_cm:
                await self._playwright_cm.__aexit__(None, None, None)
                self._playwright_cm = None
                self._playwright = None
            logger.info("browser_closed")
        except Exception as exc:
            logger.warning("browser_close_error", error=str(exc))
