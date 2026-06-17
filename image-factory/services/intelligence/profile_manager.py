from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from configs.logging import get_logger
from configs.settings import settings
from services.intelligence.models import MarketplaceProfile, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

PROFILES_DIR = Path(__file__).parent / "profiles"
PROFILES_REDIS_PREFIX = "intel:profile:"

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "1688.com": {
        "name": "1688",
        "selectors": {
            "title": "h1[data-spm*='title'], .product-title, .detail-title",
            "price": ".price, .product-price, .detail-price",
            "description": ".detail-desc, .product-description",
            "images": ".detail-gallery img, .product-gallery img, .tb-thumb img",
            "attributes": ".product-params, .detail-params",
        },
        "json_paths": {
            "title": "offerView.title, offerView.subject",
            "price": "offerView.price, sku.price",
            "images": "offerView.imageList, images",
            "description": "offerView.description",
        },
        "api_endpoints": [
            "https://detail.1688.com/offer/{id}.html",
            "https://offer.1688.com/offer/offerDetail.htm",
        ],
        "captcha_signatures": ["nc_login", "verify.1688.com", "slide-verify"],
        "session_rules": {
            "max_requests_per_session": 50,
            "session_ttl_hours": 24,
            "cooldown_minutes": 30,
        },
        "request_rules": {
            "max_concurrent": 2,
            "delay_min": 4.0,
            "delay_max": 8.0,
            "backoff_strategy": "exponential",
        },
    },
    "taobao.com": {
        "name": "Taobao",
        "selectors": {
            "title": ".tb-main-title, .title, h1[data-spm]",
            "price": ".tb-rmb-num, .price, .tm-price",
            "description": ".tb-detail-desc, .desc-wrap",
            "images": "#J_ImgBooth img, .tb-thumb img, .item-photo img",
        },
        "json_paths": {
            "title": "itemInfoModel.title, api.item.title",
            "price": "itemInfoModel.price, api.item.price",
            "images": "itemInfoModel.images, api.item.images",
        },
        "captcha_signatures": ["umid", "h5_nc", "nocaptcha"],
        "session_rules": {
            "max_requests_per_session": 30,
            "session_ttl_hours": 12,
            "cooldown_minutes": 60,
        },
        "request_rules": {
            "max_concurrent": 2,
            "delay_min": 5.0,
            "delay_max": 10.0,
            "backoff_strategy": "exponential",
        },
    },
    "tmall.com": {
        "name": "Tmall",
        "selectors": {
            "title": ".tb-main-title, .title, h1",
            "price": ".tm-price, .price",
            "description": ".detail-desc, .desc-wrap",
            "images": "#J_ImgBooth img, .tm-gallery img",
        },
        "json_paths": {
            "title": "itemModel.title, api.item.title",
            "price": "itemModel.price, api.item.price",
            "images": "itemModel.images, api.item.images",
        },
        "captcha_signatures": ["h5_nc", "nocaptcha"],
        "session_rules": {
            "max_requests_per_session": 30,
            "session_ttl_hours": 12,
            "cooldown_minutes": 60,
        },
        "request_rules": {
            "max_concurrent": 2,
            "delay_min": 5.0,
            "delay_max": 10.0,
            "backoff_strategy": "exponential",
        },
    },
    "alibaba.com": {
        "name": "Alibaba",
        "selectors": {
            "title": "h1[class*='title'], .product-title",
            "price": ".product-price, .price",
            "description": ".product-description, .detail-description",
            "images": ".product-gallery img, .image-gallery img",
        },
        "json_paths": {
            "title": "pageData.title, product.title",
            "price": "pageData.price, product.price",
            "images": "pageData.images, product.images",
        },
        "captcha_signatures": ["captcha.alibaba", "aliyun-captcha"],
        "session_rules": {
            "max_requests_per_session": 40,
            "session_ttl_hours": 24,
            "cooldown_minutes": 30,
        },
        "request_rules": {
            "max_concurrent": 3,
            "delay_min": 3.0,
            "delay_max": 7.0,
            "backoff_strategy": "exponential",
        },
    },
    "aliexpress.com": {
        "name": "AliExpress",
        "selectors": {
            "title": "h1[class*='title'], .product-title-text",
            "price": ".product-price-value, .price",
            "description": ".product-description, .detail-description",
            "images": ".image-viewer img, .gallery-item img",
        },
        "json_paths": {
            "title": "data.title, pageData.title",
            "price": "data.price, pageData.price",
            "images": "data.images, pageData.imageList",
        },
        "captcha_signatures": ["recaptcha", "hcaptcha", "ali.captcha"],
        "session_rules": {
            "max_requests_per_session": 50,
            "session_ttl_hours": 24,
            "cooldown_minutes": 20,
        },
        "request_rules": {
            "max_concurrent": 3,
            "delay_min": 3.0,
            "delay_max": 6.0,
            "backoff_strategy": "exponential",
        },
    },
    "jd.com": {
        "name": "JD",
        "selectors": {
            "title": ".sku-name, .item-title, h1",
            "price": ".price, .jd-price, .p-price",
            "description": ".detail-desc, .product-desc",
            "images": ".spec-items img, .gallery img",
        },
        "json_paths": {
            "title": "itemInfo.skuName, page.title",
            "price": "itemInfo.price, page.price",
            "images": "itemInfo.imageList, page.images",
        },
        "captcha_signatures": ["jd-captcha", "slide.jd.com"],
        "session_rules": {
            "max_requests_per_session": 60,
            "session_ttl_hours": 48,
            "cooldown_minutes": 15,
        },
        "request_rules": {
            "max_concurrent": 4,
            "delay_min": 2.0,
            "delay_max": 5.0,
            "backoff_strategy": "linear",
        },
    },
    "pinduoduo.com": {
        "name": "Pinduoduo",
        "selectors": {
            "title": ".goods-title, .product-title, h1",
            "price": ".goods-price, .price",
            "description": ".goods-desc, .product-desc",
            "images": ".goods-gallery img, .swiper-slide img",
        },
        "json_paths": {
            "title": "goodsInfo.title, product.name",
            "price": "goodsInfo.price, product.price",
            "images": "goodsInfo.gallery, product.images",
        },
        "captcha_signatures": ["pinduoduo-captcha"],
        "session_rules": {
            "max_requests_per_session": 20,
            "session_ttl_hours": 6,
            "cooldown_minutes": 120,
        },
        "request_rules": {
            "max_concurrent": 1,
            "delay_min": 8.0,
            "delay_max": 15.0,
            "backoff_strategy": "exponential",
        },
    },
}


class MarketplaceProfileManager:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self.emitter = emitter or EventEmitter()
        self._cache: dict[str, MarketplaceProfile] = {}
        self._profiles_dir = PROFILES_DIR

    def _domain_key(self, domain: str) -> str:
        return domain.replace("www.", "").strip()

    async def get_profile(self, domain: str) -> MarketplaceProfile | None:
        domain = self._domain_key(domain)
        if domain in self._cache:
            return self._cache[domain]

        profile_path = self._profiles_dir / f"{domain}.json"
        if profile_path.exists():
            try:
                data = json.loads(profile_path.read_text(encoding="utf-8"))
                profile = MarketplaceProfile.from_dict(data)
                self._cache[domain] = profile
                return profile
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("profile_load_failed", domain=domain, error=str(exc))

        if domain in DEFAULT_PROFILES:
            profile = MarketplaceProfile.from_dict({
                "domain": domain,
                **DEFAULT_PROFILES[domain],
            })
            self._cache[domain] = profile
            await self._save_to_disk(domain, profile)
            return profile

        return None

    async def save_profile(self, domain: str, profile: MarketplaceProfile) -> None:
        domain = self._domain_key(domain)
        self._cache[domain] = profile
        profile.last_updated = datetime.utcnow().isoformat()
        await self._save_to_disk(domain, profile)
        await self.emitter.emit(IntelligenceEventType.MARKETPLACE_PROFILE_UPDATED, domain, {
            "preferred_method": profile.preferred_extraction_method,
        })

    async def _save_to_disk(self, domain: str, profile: MarketplaceProfile) -> None:
        profile_path = self._profiles_dir / f"{domain}.json"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    async def update_selectors(self, domain: str, selectors: dict[str, str]) -> None:
        profile = await self.get_profile(domain)
        if profile:
            profile.selectors.update(selectors)
            await self.save_profile(domain, profile)

    async def add_captcha_signature(self, domain: str, signature: str) -> None:
        profile = await self.get_profile(domain)
        if profile and signature not in profile.captcha_signatures:
            profile.captcha_signatures.append(signature)
            await self.save_profile(domain, profile)

    async def add_redirect_pattern(self, domain: str, pattern: str) -> None:
        profile = await self.get_profile(domain)
        if profile and pattern not in profile.redirect_patterns:
            profile.redirect_patterns.append(pattern)
            await self.save_profile(domain, profile)

    async def get_all_profiles(self) -> list[MarketplaceProfile]:
        profiles: list[MarketplaceProfile] = []
        all_domains = set(DEFAULT_PROFILES.keys())
        for f in self._profiles_dir.glob("*.json"):
            domain = f.stem
            all_domains.add(domain)
        for domain in all_domains:
            profile = await self.get_profile(domain)
            if profile:
                profiles.append(profile)
        return profiles

    async def profile_exists(self, domain: str) -> bool:
        domain = self._domain_key(domain)
        if domain in self._cache:
            return True
        profile_path = self._profiles_dir / f"{domain}.json"
        if profile_path.exists():
            return True
        return domain in DEFAULT_PROFILES

    async def close(self) -> None:
        self._cache.clear()
