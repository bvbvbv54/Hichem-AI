from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.models import AcquisitionJob, AcquisitionResult, FailureType
from services.acquisition.http_client import HardenedHTTPClient
from services.acquisition.detector import AntiBotDetector
from services.acquisition.rate_limiter import DomainRateLimiter
from services.acquisition.robots_checker import RobotsChecker
from services.acquisition.image_extractor import extract_image_urls, extract_page_title, extract_page_description, extract_images_for_domain, validate_product_page
from services.acquisition.image_downloader import ImageDownloader
from services.acquisition.cache import ImageCache
from services.acquisition.monitor import AcquisitionMonitor
from services.acquisition.queue_manager import AcquisitionQueue
from services.acquisition.browser_client import BrowserClient
from services.acquisition.scrapfly_client import ScrapflyClient
from services.pipeline.errors import PipelineError, ErrorCode, ErrorSeverity
from services.admin_notifier import get_notifier

logger = get_logger(__name__)

_CN_PRIMARY_DOMAINS = {"1688.com", "taobao.com", "tmall.com", "detail.1688.com", "alibaba.com", "aliexpress.com"}
_VALIDATE_PAGE_DOMAINS = {"alibaba.com", "www.alibaba.com"}
_AMAZON_DOMAINS = {"amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr", "amazon.it", "amazon.es", "amazon.ca", "amazon.in", "amazon.com.au", "amazon.com.br", "amazon.com.mx", "amazon.nl", "amazon.pl", "amazon.se", "amazon.sg", "amazon.ae", "amazon.sa"}

_CAPTCHA_TITLES = {
    "验证码拦截", "just a moment", "please wait", "attention required",
    "verify you are human", "captcha", "bot detection", "access denied",
    "sorry, you have been blocked", "please enable cookies",
}

_CN_CAPTCHA_TITLES = {
    "验证码", "安全验证", "人机验证", "访问被拒绝", "请求被拦截",
}


def _is_captcha_page(title: str, html: str | None = None) -> bool:
    title_lower = title.lower()
    for kw in _CAPTCHA_TITLES:
        if kw in title_lower:
            return True
    for kw in _CN_CAPTCHA_TITLES:
        if kw in title:
            return True
    if html:
        if "window._cf_chl" in html or "cf_challenge" in html:
            return True
        if "g-recaptcha" in html or "h-captcha" in html:
            return True
    return False


_ALI_THUMB_RE = re.compile(
    r"^(.*?\.(?:jpg|jpeg|png|webp|avif|gif))[._]?\d+x\d+\w*\..*$",
    re.I,
)

_THUMB_DIMS_RE = re.compile(
    r"(.*?)[._](\d+)x(\d+)(?:\w*)\.(jpg|jpeg|png|webp|avif|gif)(\?.*)?$",
    re.I,
)


def _normalize_image_url(url: str) -> str:
    qs_idx = url.find("?")
    path_part = url[:qs_idx] if qs_idx > -1 else url

    # Pattern 1: alicdn-style thumbnails:  pic.jpg_100x100.jpg, pic.png_100x100Q75.png
    m = _ALI_THUMB_RE.match(path_part)
    if m:
        base = m.group(1)
        return base + (url[qs_idx:] if qs_idx > -1 else "")

    # Pattern 2: generic thumbnail dimensions:  /path/pic_100x100.jpg, /100x100/pic.jpg
    m = _THUMB_DIMS_RE.match(path_part)
    if m:
        base = m.group(1)
        ext = m.group(4)
        w, h = int(m.group(2)), int(m.group(3))
        if w < 400 or h < 400:
            return f"{base}.{ext}"
        return url

    m = re.match(r"^(https?://[^/]+(?:/[^/]+)*?)/\d+x\d+\.(?:jpg|jpeg|png|webp|gif|avif)$", url, re.I)
    if m:
        base = m.group(1)
        ext = url.rsplit(".", 1)[-1]
        return f"{base}.{ext}"

    stripped = re.sub(r"\.slim\.\w+(?:\?.*)?$", "", url, re.I)
    if stripped != url:
        return stripped.split("?")[0]

    cleaned = re.sub(r"[?&]x-oss-process[^&]*", "", url)
    if cleaned != url:
        return cleaned.rstrip("?")

    if ".jpg_.webp" in url or ".jpg_.avif" in url or ".jpg_.png" in url:
        return url.replace(".jpg_.webp", ".jpg").replace(".jpg_.avif", ".jpg").replace(".jpg_.png", ".jpg")

    # Pattern 3: Known size suffixes like _220x220q75.jpg
    cleaned2 = re.sub(r"[._](\d+)x(\d+)[a-zA-Z0-9]*\.(jpg|jpeg|png|webp|avif|gif)", r".\3", path_part, re.I)
    if cleaned2 != path_part:
        cleaned2 += url[qs_idx:] if qs_idx > -1 else ""
        return cleaned2

    return url


class AcquisitionPipeline:
    def __init__(self) -> None:
        self.http_client = HardenedHTTPClient()
        self.detector = AntiBotDetector()
        self.rate_limiter = DomainRateLimiter()
        self.robots_checker = RobotsChecker()
        self.downloader = ImageDownloader(self.http_client)
        self.cache = ImageCache(self.downloader)
        self.monitor = AcquisitionMonitor()
        self.queue = AcquisitionQueue()
        self.browser = BrowserClient()
        self.scrapfly = ScrapflyClient()
        self._consecutive_blocks: dict[str, int] = {}

    async def run(self, job: AcquisitionJob) -> AcquisitionResult:
        notifier = get_notifier()
        start = time.monotonic()
        domain = urlparse(job.url).netloc.replace("www.", "")

        is_cn_domain = any(d in domain for d in _CN_PRIMARY_DOMAINS)
        is_amazon_domain = any(d in domain for d in _AMAZON_DOMAINS)

        logger.info("pipeline_start", job_id=job.job_id, url=job.url)

        if await self.queue.is_restricted(domain):
            return AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=FailureType.BOT_BLOCKED,
                failure_detail="Domain is restricted due to repeated blocks",
                duration_ms=0,
            )

        allowed, failure = await self.robots_checker.is_allowed(job.url)
        if not allowed:
            await notifier.notify(PipelineError(
                code=ErrorCode.ACQ_ROBOTS_DISALLOWED,
                severity=ErrorSeverity.INFO,
                message=f"robots.txt disallows scraping: {job.url} — product skipped.",
                job_id=job.job_id,
                stage="acquisition",
                product_url=job.url,
                retryable=False,
            ))
            result = AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=failure,
                failure_detail="Disallowed by robots.txt",
                duration_ms=(time.monotonic() - start) * 1000,
            )
            await self.monitor.record(result)
            return result

        crawl_delay = self.robots_checker.get_crawl_delay(domain)
        if crawl_delay > 0:
            self.rate_limiter._local_buckets[domain]._rate = min(
                self.rate_limiter._local_buckets[domain]._rate, 1.0 / crawl_delay
            )

        await self.rate_limiter.acquire(domain)

        html, used_browser, api_images, failure_type, failure_detail = await self._fetch_page(job.url)

        if failure_type and failure_detail:
            if failure_type in (FailureType.BOT_BLOCKED, FailureType.CAPTCHA):
                self._consecutive_blocks[domain] = self._consecutive_blocks.get(domain, 0) + 1
                if self._consecutive_blocks[domain] >= 3:
                    await self.queue.mark_restricted(domain)

            code_map = {
                FailureType.CAPTCHA: ErrorCode.ACQ_CAPTCHA,
                FailureType.BOT_BLOCKED: ErrorCode.ACQ_BOT_BLOCKED,
                FailureType.RATE_LIMITED: ErrorCode.ACQ_RATE_LIMITED,
                FailureType.TIMEOUT: ErrorCode.ACQ_TIMEOUT,
            }
            code = code_map.get(failure_type, ErrorCode.ACQ_NETWORK_ERROR)
            severity = ErrorSeverity.WARNING if failure_type in (FailureType.CAPTCHA, FailureType.BOT_BLOCKED) else ErrorSeverity.INFO
            msg = {
                FailureType.CAPTCHA: f"CAPTCHA encountered on {job.url} — automated access blocked. Manual download required.",
                FailureType.BOT_BLOCKED: f"Bot detection triggered on {job.url} — domain marked restricted for 1 hour.",
                FailureType.RATE_LIMITED: f"Rate limited by {job.url} — backoff applied.",
            }.get(failure_type, f"Acquisition failed: {failure_detail}")

            await notifier.notify(PipelineError(
                code=code,
                severity=severity,
                message=msg,
                job_id=job.job_id,
                stage="acquisition",
                product_url=job.url,
                retryable=failure_type == FailureType.RATE_LIMITED,
            ))

            result = AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=failure_type,
                failure_detail=failure_detail,
                required_browser=used_browser,
                duration_ms=(time.monotonic() - start) * 1000,
            )
            await self.monitor.record(result)
            return result

        if not html:
            result = AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=FailureType.PAGE_STRUCTURE_CHANGED,
                failure_detail="No HTML content retrieved",
                duration_ms=(time.monotonic() - start) * 1000,
            )
            await self.monitor.record(result)
            return result

        self._consecutive_blocks[domain] = 0

        page_title = extract_page_title(html)
        page_description = extract_page_description(html)

        # Validate page is not a CAPTCHA/bot page
        if _is_captcha_page(page_title, html):
            logger.warning("captcha_page_detected", job_id=job.job_id, url=job.url, title=page_title)
            result = AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=FailureType.CAPTCHA,
                failure_detail=f"CAPTCHA page detected: {page_title}",
                required_browser=used_browser,
                duration_ms=(time.monotonic() - start) * 1000,
            )
            await self.monitor.record(result)
            await self.queue.mark_restricted(domain)
            return result

        image_urls = extract_images_for_domain(html, job.url, domain)
        image_urls = [_normalize_image_url(u) for u in image_urls]
        image_urls = list(dict.fromkeys(image_urls))
        if api_images:
            normalized_api = [_normalize_image_url(u) for u in api_images]
            for u in normalized_api:
                if u not in image_urls:
                    image_urls.append(u)
        image_urls = image_urls[:job.max_images]

        if not image_urls:
            if settings.scrapfly_enabled:
                logger.info("falling_back_to_scrapfly", url=job.url)
                sf_html = await self.scrapfly.fetch_page(
                    job.url, render_js=True,
                    country="cn" if is_cn_domain else ("us" if is_amazon_domain else None),
                )
                if sf_html and not _is_captcha_page(extract_page_title(sf_html), sf_html):
                    sf_valid = True
                    if domain in _VALIDATE_PAGE_DOMAINS:
                        sf_valid, reason = validate_product_page(job.url, sf_html)
                        if not sf_valid:
                            logger.warning("fallback_scrapfly_validation_failed", reason=reason)
                    if sf_valid:
                        sf_urls = extract_images_for_domain(sf_html, job.url, domain)
                        image_urls = [_normalize_image_url(u) for u in sf_urls]
                        page_title = extract_page_title(sf_html) or page_title
                        page_description = extract_page_description(sf_html) or page_description
                        image_urls = image_urls[:job.max_images]

        if not image_urls and not used_browser and settings.use_browser_fallback:
            logger.info("falling_back_to_browser", url=job.url)
            browser_html, api_images = await self.browser.fetch_page_with_api(job.url)
            if browser_html and not _is_captcha_page(extract_page_title(browser_html), browser_html):
                b_valid = True
                if domain in _VALIDATE_PAGE_DOMAINS:
                    b_valid, reason = validate_product_page(job.url, browser_html)
                    if not b_valid:
                        logger.warning("fallback_browser_validation_failed", reason=reason)
                if b_valid:
                    browser_urls = extract_images_for_domain(browser_html, job.url, domain)
                browser_urls = [_normalize_image_url(u) for u in browser_urls]
                browser_urls = list(dict.fromkeys(browser_urls))
                if api_images:
                    normalized_api = [_normalize_image_url(u) for u in api_images]
                    browser_urls.extend(normalized_api)
                    browser_urls = list(dict.fromkeys(browser_urls))
                if browser_urls:
                    image_urls = browser_urls[:job.max_images]
                    used_browser = True
                    page_title = extract_page_title(browser_html) or page_title
                    page_description = extract_page_description(browser_html) or page_description

        if not image_urls and "temu.com" in job.url:
            logger.info("falling_back_to_temu_api", url=job.url)
            temu_urls = await _fetch_temu_images(job.url)
            if temu_urls:
                image_urls = temu_urls[:job.max_images]

        if not image_urls:
            result = AcquisitionResult(
                job_id=job.job_id,
                url=job.url,
                success=False,
                failure_type=FailureType.PAGE_STRUCTURE_CHANGED,
                failure_detail="No image URLs found in page",
                duration_ms=(time.monotonic() - start) * 1000,
            )
            await self.monitor.record(result)
            return result

        image_paths: list[str] = []
        image_hashes: list[str] = []
        seen_paths: set[str] = set()
        was_cached = True

        checkpoint = await self.queue.load_checkpoint(job.job_id)
        downloaded_urls = set(checkpoint.get("downloaded_urls", []))

        for img_url in image_urls:
            if img_url in downloaded_urls:
                logger.info("skipping_already_downloaded", url=img_url)
                continue
            path, cached = await self.cache.get_or_download(img_url, job.job_id)
            if path:
                if path not in seen_paths:
                    seen_paths.add(path)
                    image_paths.append(path)
                    image_hashes.append(hashlib.sha256(path.encode()).hexdigest())
                downloaded_urls.add(img_url)
                if not cached:
                    was_cached = False
            if len(image_paths) >= job.max_images:
                break

        await self.queue.save_checkpoint(job.job_id, {"downloaded_urls": list(downloaded_urls)})
        await self.rate_limiter.record_success(domain)

        duration_ms = (time.monotonic() - start) * 1000
        result = AcquisitionResult(
            job_id=job.job_id,
            url=job.url,
            success=len(image_paths) > 0,
            image_paths=image_paths,
            image_hashes=image_hashes,
            page_title=page_title,
            page_description=page_description,
            required_browser=used_browser,
            was_cached=was_cached,
            duration_ms=duration_ms,
        )
        await self.monitor.record(result)

        if not image_paths:
            await notifier.notify(PipelineError(
                code=ErrorCode.ACQ_NO_IMAGES_FOUND,
                severity=ErrorSeverity.WARNING,
                message=f"No images could be downloaded from {job.url} — page structure may have changed.",
                job_id=job.job_id,
                stage="acquisition",
                product_url=job.url,
                retryable=False,
            ))

        logger.info("pipeline_complete", job_id=job.job_id, images=len(image_paths), duration_ms=duration_ms)
        return result

    async def _fetch_page(self, url: str) -> tuple[str | None, bool, list[str], FailureType | None, str | None]:
        domain = urlparse(url).netloc.replace("www.", "")

        # For Chinese e-commerce sites, use Scrapfly with country=cn as primary
        is_cn_domain = any(d in domain for d in _CN_PRIMARY_DOMAINS)

        if is_cn_domain and settings.scrapfly_enabled:
            logger.info("scrapfly_primary_cn", url=url)
            html = await self.scrapfly.fetch_page(url, render_js=True, country="cn")
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    if domain in _VALIDATE_PAGE_DOMAINS:
                        is_valid, reason = validate_product_page(url, html)
                        if is_valid:
                            image_urls = extract_images_for_domain(html, url, domain)
                            if image_urls:
                                return html, False, [], None, None
                        logger.warning("page_validation_failed", url=url, reason=reason)
                    else:
                        image_urls = extract_images_for_domain(html, url, domain)
                        if image_urls:
                            return html, False, [], None, None
                logger.warning("scrapfly_primary_captcha", url=url, title=title)
            # If Scrapfly returned CAPTCHA, fall through to browser for CN domains
            logger.info("scrapfly_cn_fallback_browser", url=url)
            html, api_images = await self.browser.fetch_page_with_api(url)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    if domain in _VALIDATE_PAGE_DOMAINS:
                        is_valid, reason = validate_product_page(url, html)
                        if is_valid:
                            image_urls = extract_images_for_domain(html, url, domain)
                            if image_urls:
                                return html, True, api_images, None, None
                        logger.warning("page_validation_failed", url=url, reason=reason)
                    else:
                        image_urls = extract_images_for_domain(html, url, domain)
                        if image_urls:
                            return html, True, api_images, None, None
                logger.warning("browser_cn_captcha", url=url, title=title)

        # For Amazon, use Scrapfly with country=us as primary
        is_amazon_domain = any(d in domain for d in _AMAZON_DOMAINS)
        if is_amazon_domain and settings.scrapfly_enabled:
            logger.info("scrapfly_primary_amazon", url=url)
            html = await self.scrapfly.fetch_page(url, render_js=True, country="us")
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    amz_urls = extract_images_for_domain(html, url, domain)
                    if amz_urls:
                        logger.info("scrapfly_amazon_success", url=url, images=len(amz_urls))
                        return html, False, [], None, None
                logger.warning("scrapfly_amazon_captcha", url=url, title=title)
            # Fallback: browser for Amazon
            logger.info("fallback_browser_amazon", url=url)
            html, api_images = await self.browser.fetch_page_with_api(url)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    amz_urls = extract_images_for_domain(html, url, domain)
                    if amz_urls:
                        return html, True, api_images, None, None
                logger.warning("browser_amazon_captcha", url=url, title=title)

        if settings.use_browser_primary:
            logger.info("browser_primary", url=url)
            html, api_images = await self.browser.fetch_page_with_api(url)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    image_urls = extract_images_for_domain(html, url, domain)
                    if image_urls or not settings.scrapfly_enabled:
                        return html, True, api_images, None, None
                logger.warning("browser_primary_captcha", url=url, title=title)

        try:
            response = await self.http_client.fetch_with_retry(url)
            elapsed = response.elapsed.total_seconds() * 1000
            failure = self.detector.classify(response, elapsed)
            if failure:
                if failure == FailureType.RATE_LIMITED:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        await self.rate_limiter.block_domain(domain, float(retry_after))
                return None, False, [], failure, f"Detected: {failure.value}"
            if not is_cn_domain:
                html = response.text
                image_urls = extract_images_for_domain(html, url, domain)
                if image_urls:
                    return html, False, [], None, None
        except Exception as exc:
            logger.info("http_fetch_failed", url=url, error=str(exc))

        # Fallback chain: browser -> scrapfly -> scrapfly (no JS)
        if settings.use_browser_fallback:
            logger.info("fallback_browser", url=url)
            html, api_images = await self.browser.fetch_page_with_api(url)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    return html, True, api_images, None, None
                logger.warning("browser_captcha_page", url=url, title=title)

        if settings.scrapfly_enabled:
            logger.info("fallback_scrapfly", url=url)
            html = await self.scrapfly.fetch_page(url, render_js=True, country="cn" if is_cn_domain else None)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    return html, False, [], None, None
                logger.warning("scrapfly_captcha_page", url=url, title=title)

        # Final attempt: Scrapfly without JS
        if settings.scrapfly_enabled:
            logger.info("fallback_scrapfly_nojs", url=url)
            html = await self.scrapfly.fetch_page(url, render_js=False, country="cn" if is_cn_domain else None)
            if html:
                title = extract_page_title(html)
                if not _is_captcha_page(title, html):
                    return html, False, [], None, None
                logger.warning("scrapfly_nojs_captcha_page", url=url, title=title)

        failure_type = FailureType.NETWORK_ERROR
        failure_detail = "All fetch methods failed"
        return None, False, [], failure_type, failure_detail

    async def close(self) -> None:
        await self.http_client.close()
        await self.rate_limiter.close()
        await self.robots_checker.close()
        await self.cache.close()
        await self.monitor.close()
        await self.queue.close()
        await self.browser.close()
        await self.scrapfly.close()


_TEMU_GOODS_ID_RE = re.compile(r"g-(\d{12,})")
_TEMU_API_URL = "https://www.temu.com/api/oak/integration/render"


async def _fetch_temu_images(page_url: str) -> list[str]:
    m = _TEMU_GOODS_ID_RE.search(page_url)
    if not m:
        m = re.search(r"goods_id[=\\\/](\d{12,})", page_url)
    goods_id = m.group(1) if m else None
    if not goods_id:
        return []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(
                _TEMU_API_URL,
                params={"goods_id": goods_id, "client": "PC"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            goods = data.get("goods", data)
            if not goods or not isinstance(goods, dict):
                goods = data.get("result", {})
            if not goods or not isinstance(goods, dict):
                return []
            urls: list[str] = []
            hd_thumb = goods.get("hd_thumb_url", "")
            if hd_thumb and hd_thumb.startswith("http"):
                urls.append(hd_thumb)
            for field in ("gallery_urls", "goods_gallery", "images", "specs"):
                field_val = goods.get(field, [])
                if isinstance(field_val, list):
                    for item in field_val:
                        if isinstance(item, str) and item.startswith("http"):
                            urls.append(item)
                        elif isinstance(item, dict):
                            for key in ("url", "src", "image", "hd_url"):
                                val = item.get(key, "")
                                if val and isinstance(val, str) and val.startswith("http"):
                                    urls.append(val)
            return urls
    except Exception:
        return []
