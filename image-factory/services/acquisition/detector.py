from __future__ import annotations

import re
from typing import Any

import httpx

from services.acquisition.models import FailureType
from configs.logging import get_logger

logger = get_logger(__name__)

_CLOUDFLARE_TITLE_PATTERN = re.compile(r"<title>\s*Just a moment\.\.\.\s*</title>", re.IGNORECASE)
_CLOUDFLARE_JS_PATTERN = re.compile(r"window\._cf_chl", re.IGNORECASE)
_CAPTCHA_PATTERN = re.compile(
    r"(captcha|recaptcha|hcaptcha|g-recaptcha|h-captcha)",
    re.IGNORECASE,
)


class AntiBotDetector:
    def classify(self, response: httpx.Response, elapsed_ms: float) -> FailureType | None:
        status = response.status_code
        headers = response.headers
        body: str | None = None

        if status == 429:
            logger.info("rate_limited_detected", url=str(response.url))
            return FailureType.RATE_LIMITED

        if status == 403:
            if "CF-RAY" in headers or headers.get("cf-cache-status", "").lower() in ("hit", "miss", "dynamic"):
                logger.info("bot_blocked_cloudflare", url=str(response.url))
                return FailureType.BOT_BLOCKED
            return FailureType.AUTH_REQUIRED

        if status in (401, 407):
            return FailureType.AUTH_REQUIRED

        if elapsed_ms > 25000:
            logger.info("timeout_detected", url=str(response.url), elapsed_ms=elapsed_ms)
            return FailureType.TIMEOUT

        if status == 200:
            body = response.text

            if _CLOUDFLARE_TITLE_PATTERN.search(body) or _CLOUDFLARE_JS_PATTERN.search(body):
                logger.info("cloudflare_js_challenge", url=str(response.url))
                return FailureType.BOT_BLOCKED

            if _CAPTCHA_PATTERN.search(body):
                logger.info("captcha_detected", url=str(response.url))
                return FailureType.CAPTCHA

        return None

    def classify_exception(self, exc: Exception) -> FailureType:
        if isinstance(exc, httpx.TimeoutException):
            return FailureType.TIMEOUT
        return FailureType.NETWORK_ERROR
