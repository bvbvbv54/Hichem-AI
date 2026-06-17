from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import (
    CaptchaEvent,
    ChallengeType,
    IntelligenceEventType,
)
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

CAPTCHA_KEY_PREFIX = "intel:captcha:"
CAPTCHA_INDEX_PREFIX = "intel:captcha_index:"
CAPTCHA_STATS_PREFIX = "intel:captcha_stats:"
CAPTCHA_SIGNATURE_PREFIX = "intel:captcha_sig:"

_CAPTCHA_SIGNATURES: dict[str, list[str]] = {
    "1688.com": [
        "nc_login",
        "verify.1688.com",
        "slide-verify",
    ],
    "taobao.com": [
        "umid",
        "h5_nc",
        "nocaptcha",
        "tbsd.taobao.com",
    ],
    "tmall.com": [
        "h5_nc",
        "nocaptcha",
    ],
    "alibaba.com": [
        "captcha.alibaba",
        "aliyun-captcha",
    ],
    "aliexpress.com": [
        "recaptcha",
        "hcaptcha",
        "ali.captcha",
    ],
    "jd.com": [
        "jd-captcha",
        "slide.jd.com",
    ],
    "pinduoduo.com": [
        "pinduoduo-captcha",
    ],
}


class CaptchaManager:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self._redis: aioredis.Redis | None = None
        self.emitter = emitter or EventEmitter()

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    def detect_challenge(self, domain: str, html: str, url: str) -> ChallengeType | None:
        html_lower = html.lower()
        html_signature = self._compute_html_signature(html)

        signatures = _CAPTCHA_SIGNATURES.get(domain, [])
        for sig in signatures:
            if sig.lower() in html_lower:
                logger.info("captcha_sig_matched", domain=domain, signature=sig)
                return ChallengeType.CAPTCHA

        if "recaptcha" in html_lower or "g-recaptcha" in html_lower:
            return ChallengeType.RECAPTCHA
        if "h-captcha" in html_lower or "hcaptcha" in html_lower:
            return ChallengeType.HCAPTCHA
        if "cf_chl" in html_lower or "cloudflare" in html_lower and "just a moment" in html_lower:
            return ChallengeType.CLOUDFLARE_JS
        if "cf-turnstile" in html_lower:
            return ChallengeType.CLOUDFLARE_TURNSTILE
        if "login" in html_lower and ("password" in html_lower or "sign in" in html_lower):
            if len(html) < 5000:
                return ChallengeType.LOGIN_CHALLENGE
        if "captcha" in html_lower or "verify" in html_lower:
            challenge_words = ["slide", "puzzle", "verify", "security check", "authentication"]
            if any(w in html_lower for w in challenge_words):
                return ChallengeType.CAPTCHA

        return None

    def _compute_html_signature(self, html: str) -> str:
        return hashlib.sha256(html[:2000].encode()).hexdigest()[:16]

    def is_redirect_suspicious(self, redirect_chain: list[str], original_url: str) -> bool:
        suspicious_domains = [
            "verify",
            "captcha",
            "challenge",
            "security",
            "authentication",
        ]
        for redirect in redirect_chain[1:]:
            for sd in suspicious_domains:
                if sd in redirect.lower():
                    return True
        return False

    async def record_event(
        self,
        domain: str,
        session_id: str,
        url: str,
        challenge_type: ChallengeType,
        html: str,
        marketplace: str = "",
    ) -> CaptchaEvent:
        redis_conn = await self._get_redis()
        event_id = str(uuid.uuid4())
        html_signature = self._compute_html_signature(html)
        event = CaptchaEvent(
            id=event_id,
            domain=domain,
            timestamp=datetime.utcnow().isoformat(),
            session_id=session_id,
            url=url,
            challenge_type=challenge_type,
            html_signature=html_signature,
            marketplace=marketplace or domain,
        )
        key = f"{CAPTCHA_KEY_PREFIX}{event_id}"
        await redis_conn.set(key, json.dumps(event.to_dict()), ex=86400 * 30)
        date_key = datetime.utcnow().strftime("%Y-%m-%d")
        index_key = f"{CAPTCHA_INDEX_PREFIX}{domain}:{date_key}"
        await redis_conn.sadd(index_key, event_id)
        await redis_conn.expire(index_key, 86400 * 31)
        sig_key = f"{CAPTCHA_SIGNATURE_PREFIX}{html_signature}"
        await redis_conn.sadd(sig_key, event_id)
        await redis_conn.expire(sig_key, 86400 * 7)
        await self._increment_stats(domain, challenge_type)
        await self.emitter.emit(IntelligenceEventType.CAPTCHA_DETECTED, marketplace or domain, {
            "event_id": event_id,
            "challenge_type": challenge_type.value,
            "session_id": session_id,
            "url": url,
        })
        logger.warning("captcha_event_recorded", domain=domain, type=challenge_type.value, session_id=session_id)
        return event

    async def _increment_stats(self, domain: str, challenge_type: ChallengeType) -> None:
        redis_conn = await self._get_redis()
        date_key = datetime.utcnow().strftime("%Y-%m-%d")
        stats_key = f"{CAPTCHA_STATS_PREFIX}{domain}:{date_key}"
        pipe = redis_conn.pipeline()
        pipe.hincrby(stats_key, "total", 1)
        pipe.hincrby(stats_key, challenge_type.value, 1)
        pipe.expire(stats_key, 86400 * 31)
        await pipe.execute()

    async def get_daily_report(self, domain: str, date_str: str | None = None) -> dict[str, Any]:
        redis_conn = await self._get_redis()
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
        stats_key = f"{CAPTCHA_STATS_PREFIX}{domain}:{date_str}"
        stats = await redis_conn.hgetall(stats_key)
        result: dict[str, Any] = {
            "domain": domain,
            "date": date_str,
            "total_captchas": 0,
        }
        if stats:
            for k, v in stats.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = int(v.decode() if isinstance(v, bytes) else v)
                result[key] = val
            result["total_captchas"] = result.pop("total", 0)
        return result

    async def get_weekly_report(self, domain: str) -> dict[str, Any]:
        redis_conn = await self._get_redis()
        now = datetime.utcnow()
        total = 0
        daily: dict[str, int] = {}
        challenge_breakdown: dict[str, int] = defaultdict(int)
        for i in range(7):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            stats_key = f"{CAPTCHA_STATS_PREFIX}{domain}:{date_str}"
            stats = await redis_conn.hgetall(stats_key)
            if stats:
                day_total = 0
                for k, v in stats.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    val = int(v.decode() if isinstance(v, bytes) else v)
                    if key == "total":
                        day_total = val
                    else:
                        challenge_breakdown[key] += val
                daily[date_str] = day_total
                total += day_total
        return {
            "domain": domain,
            "period": "7d",
            "end_date": now.strftime("%Y-%m-%d"),
            "total_captchas": total,
            "daily_breakdown": daily,
            "challenge_breakdown": dict(challenge_breakdown),
        }

    async def get_top_blocking_marketplaces(self, limit: int = 10) -> list[dict[str, Any]]:
        redis_conn = await self._get_redis()
        now = datetime.utcnow()
        domain_counts: dict[str, int] = defaultdict(int)
        for i in range(7):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            keys = await redis_conn.keys(f"{CAPTCHA_STATS_PREFIX}*:{date_str}")
            for key in keys:
                k = key.decode() if isinstance(key, bytes) else key
                parts = k.split(":")
                if len(parts) >= 4:
                    domain = parts[3]
                    stats = await redis_conn.hgetall(k)
                    total = 0
                    if stats:
                        total = int(stats.get(b"total", stats.get("total", 0)))
                    domain_counts[domain] += total
        sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"domain": d, "captcha_count": c} for d, c in sorted_domains[:limit]]

    async def is_known_captcha_page(self, html: str) -> bool:
        redis_conn = await self._get_redis()
        html_signature = self._compute_html_signature(html)
        sig_key = f"{CAPTCHA_SIGNATURE_PREFIX}{html_signature}"
        exists = await redis_conn.exists(sig_key)
        return bool(exists)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
