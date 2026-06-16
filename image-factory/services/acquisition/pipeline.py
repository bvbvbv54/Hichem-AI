from __future__ import annotations

import hashlib
import time
from urllib.parse import urlparse

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.models import AcquisitionJob, AcquisitionResult, FailureType
from services.acquisition.http_client import HardenedHTTPClient
from services.acquisition.detector import AntiBotDetector
from services.acquisition.rate_limiter import DomainRateLimiter
from services.acquisition.robots_checker import RobotsChecker
from services.acquisition.image_extractor import extract_image_urls
from services.acquisition.image_downloader import ImageDownloader
from services.acquisition.cache import ImageCache
from services.acquisition.monitor import AcquisitionMonitor
from services.acquisition.queue_manager import AcquisitionQueue
from services.acquisition.browser_client import BrowserClient
from services.pipeline.errors import PipelineError, ErrorCode, ErrorSeverity
from services.admin_notifier import get_notifier

logger = get_logger(__name__)


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
        self._consecutive_blocks: dict[str, int] = {}

    async def run(self, job: AcquisitionJob) -> AcquisitionResult:
        notifier = get_notifier()
        start = time.monotonic()
        domain = urlparse(job.url).netloc.replace("www.", "")

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

        html, used_browser, failure_type, failure_detail = await self._fetch_page(job.url)

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

        image_urls = extract_image_urls(html, job.url)
        image_urls = image_urls[:job.max_images]

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
        was_cached = True

        checkpoint = await self.queue.load_checkpoint(job.job_id)
        downloaded_urls = set(checkpoint.get("downloaded_urls", []))

        for img_url in image_urls:
            if img_url in downloaded_urls:
                logger.info("skipping_already_downloaded", url=img_url)
                continue
            path, cached = await self.cache.get_or_download(img_url, job.job_id)
            if path:
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

    async def _fetch_page(self, url: str) -> tuple[str | None, bool, FailureType | None, str | None]:
        try:
            response = await self.http_client.fetch_with_retry(url)
            elapsed = response.elapsed.total_seconds() * 1000
            failure = self.detector.classify(response, elapsed)
            if failure:
                if failure == FailureType.RATE_LIMITED:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        domain = urlparse(url).netloc
                        await self.rate_limiter.block_domain(domain, float(retry_after))
                return None, False, failure, f"Detected: {failure.value}"
            return response.text, False, None, None
        except Exception as exc:
            failure = self.detector.classify_exception(exc)
            if failure == FailureType.BOT_BLOCKED and settings.use_browser_fallback:
                logger.info("falling_back_to_browser", url=url)
                html = await self.browser.fetch_page(url)
                if html:
                    return html, True, None, None
            return None, False, failure, str(exc)

    async def close(self) -> None:
        await self.http_client.close()
        await self.rate_limiter.close()
        await self.robots_checker.close()
        await self.cache.close()
        await self.monitor.close()
        await self.queue.close()
        await self.browser.close()
