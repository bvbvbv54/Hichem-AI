from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from configs.logging import get_logger
from services.intelligence.models import MarketplaceProfile, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter
from services.intelligence.profile_manager import MarketplaceProfileManager

logger = get_logger(__name__)

_PRICE_PATTERNS = [
    re.compile(r"[\u00a5\$]?\d+[.,]\d{2}"),
    re.compile(r"price[=:]\s*[\d.]+"),
    re.compile(r"\d+[.,]\d{2}\s*(USD|CNY|HKD|EUR)"),
    re.compile(r"[\u00a5]\s*\d+"),
]

_IMAGE_PATTERNS = re.compile(
    r"(https?://[^\s\"'>]+(?:jpg|jpeg|png|webp|gif))",
    re.IGNORECASE,
)

_PRODUCT_CANDIDATE_CLASSES = [
    "product", "item", "goods", "offer", "sku",
    "detail", "card", "tile", "listing",
    "shop-item", "product-item", "goods-item",
]


class DomainDiscoverer:
    def __init__(
        self,
        profile_manager: MarketplaceProfileManager | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.profile_manager = profile_manager or MarketplaceProfileManager()
        self.emitter = emitter or EventEmitter()

    async def analyze_domain(self, url: str, html: str, domain: str = "") -> MarketplaceProfile:
        if not domain:
            domain = urlparse(url).netloc.replace("www.", "")
        soup = BeautifulSoup(html, "html.parser")

        selectors = self._discover_selectors(soup)
        image_patterns = self._discover_image_patterns(soup, url)
        price_patterns_found = self._detect_pricing_patterns(html)
        structured_data = self._extract_structured_data(soup)
        api_endpoints = self._discover_api_endpoints(html, domain)
        product_indicators = self._detect_product_indicators(soup)

        profile = MarketplaceProfile(
            domain=domain,
            name=domain.split(".")[-2].title() if len(domain.split(".")) > 1 else domain,
            selectors=selectors,
            api_endpoints=api_endpoints,
            image_patterns=image_patterns,
            last_updated=datetime.utcnow().isoformat(),
        )

        profile.successful_patterns.append({
            "discovered_at": datetime.utcnow().isoformat(),
            "url": url,
            "has_structured_data": bool(structured_data),
            "product_indicators": product_indicators,
        })

        if structured_data:
            profile.json_paths = self._discover_json_paths(structured_data)
            profile.preferred_extraction_method = "json_ld"

        if price_patterns_found:
            profile.request_rules["has_pricing"] = True

        await self.profile_manager.save_profile(domain, profile)
        await self.emitter.emit(IntelligenceEventType.NEW_DOMAIN_DISCOVERED, domain, {
            "url": url,
            "has_structured_data": bool(structured_data),
            "selector_count": len(selectors),
            "api_endpoints": len(api_endpoints),
        })

        logger.info("domain_discovered", domain=domain, selectors=len(selectors), structured_data=bool(structured_data))
        return profile

    def _discover_selectors(self, soup: BeautifulSoup) -> dict[str, str]:
        selectors: dict[str, str] = {}

        title_candidates = soup.find_all(["h1", "h2"], limit=10)
        for tag in title_candidates:
            text = tag.get_text(strip=True)
            if len(text) > 10 and len(text) < 200:
                classes = " ".join(tag.get("class", []))
                if classes:
                    selectors["title"] = f"h1.{'.'.join(classes.replace(' ', '.'))}"
                    break
                selectors["title"] = "h1"
                break

        price_candidates = soup.find_all(class_=lambda c: c and any(
            p in (c or "").lower() for p in ["price", "cost", "amount", "rmb", "currency"]
        ), limit=5)
        if price_candidates:
            tag = price_candidates[0]
            classes = " ".join(tag.get("class", []))
            tag_name = tag.name
            selectors["price"] = f"{tag_name}.{'.'.join(classes.replace(' ', '.'))}"

        img_candidates = soup.find_all("img", limit=20)
        img_selectors: list[str] = []
        for img in img_candidates:
            src = img.get("src", "")
            cls = img.get("class", [])
            if src and any(p in src.lower() for p in ["product", "goods", "item", "img", "photo", "pic"]):
                if cls:
                    img_selectors.append(f"img.{'.'.join(cls)}")
        if img_selectors:
            selectors["images"] = ", ".join(set(img_selectors[:3]))

        desc_selectors = [
            *[f".{'.'.join(c)}" for c in [tag.get("class", []) for tag in soup.find_all(class_=lambda x: x and "desc" in x.lower())[:3]]],
            *[f"#{tag.get('id')}" for tag in soup.find_all(id=lambda x: x and "desc" in x.lower())[:3]],
        ]
        if desc_selectors:
            selectors["description"] = ", ".join(desc_selectors[:3])

        return selectors

    def _discover_image_patterns(self, soup: BeautifulSoup, base_url: str) -> dict[str, str]:
        patterns: dict[str, str] = {}
        images = soup.find_all("img", limit=30)
        for img in images:
            src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
            if src:
                full_url = urljoin(base_url, src)
                if any(p in full_url.lower() for p in [".jpg", ".jpeg", ".png", ".webp"]):
                    attr = "src"
                    if img.get("data-src"):
                        attr = "data-src"
                    elif img.get("data-original"):
                        attr = "data-original"
                    patterns[attr] = attr
                    break
        return patterns

    def _detect_pricing_patterns(self, html: str) -> list[str]:
        found = []
        for pattern in _PRICE_PATTERNS:
            matches = pattern.findall(html)
            if matches:
                found.extend(matches[:5])
        return found

    def _extract_structured_data(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _discover_json_paths(self, structured_data: dict[str, Any]) -> dict[str, str]:
        paths: dict[str, str] = {}
        if "name" in structured_data:
            paths["title"] = "name"
        if "offers" in structured_data:
            paths["price"] = "offers.price"
        if "image" in structured_data:
            paths["images"] = "image"
        if "description" in structured_data:
            paths["description"] = "description"
        return paths

    def _discover_api_endpoints(self, html: str, domain: str) -> list[str]:
        endpoints: list[str] = []
        api_pattern = re.compile(
            r'(?:https?://(?:api|rest|service|gateway)\.' + re.escape(domain) + r'[^\s"\'<>]+)',
            re.IGNORECASE,
        )
        endpoints = list(set(api_pattern.findall(html)))
        xhr_pattern = re.compile(r'(?:fetch|XMLHttpRequest|axios|ajax)\([\'\"]([^\'"]+)[\'\"]')
        for match in xhr_pattern.finditer(html):
            url_path = match.group(1)
            if url_path.startswith("/"):
                full_url = f"https://{domain}{url_path}"
                if full_url not in endpoints:
                    endpoints.append(full_url)
        return endpoints[:10]

    def _detect_product_indicators(self, soup: BeautifulSoup) -> dict[str, Any]:
        indicators: dict[str, Any] = {
            "has_product_class": False,
            "has_gallery": False,
            "has_price_text": False,
            "has_add_to_cart": False,
            "product_candidate_count": 0,
        }

        for cls in _PRODUCT_CANDIDATE_CLASSES:
            if soup.find_all(class_=lambda c: c and cls in (c or "").lower(), limit=5):
                indicators["has_product_class"] = True
                indicators["product_candidate_count"] += len(soup.select(f"[class*='{cls}']"))

        if soup.find_all(class_=lambda c: c and any(
            g in (c or "").lower() for g in ["gallery", "carousel", "slider", "swiper"]
        ), limit=3):
            indicators["has_gallery"] = True

        body_text = soup.get_text().lower()
        if any(p in body_text for p in ["price", "$", "\u00a5", "rmb", "cost"]):
            indicators["has_price_text"] = True
        if any(a in body_text for a in ["add to cart", "buy now", "purchase", "add to basket"]):
            indicators["has_add_to_cart"] = True

        return indicators

    def generate_discovery_report(self, profile: MarketplaceProfile) -> dict[str, Any]:
        return {
            "domain": profile.domain,
            "name": profile.name,
            "discovered_at": profile.last_updated,
            "selectors_found": list(profile.selectors.keys()),
            "api_endpoints_found": len(profile.api_endpoints),
            "structured_data_available": bool(profile.json_paths),
            "preferred_extraction": profile.preferred_extraction_method or "not_determined",
            "product_indicators": profile.successful_patterns[0].get("product_indicators", {}) if profile.successful_patterns else {},
            "image_patterns": list(profile.image_patterns.keys()),
        }
