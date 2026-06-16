from __future__ import annotations

import json
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from configs.logging import get_logger
from services.extractor.parsers.base import BaseParser, ExtractedProduct

logger = get_logger(__name__)


class AliExpressParser(BaseParser):
    """Parser for AliExpress product pages."""

    def can_handle(self, url: str) -> bool:
        return bool(re.search(r"aliexpress\.com", url, re.IGNORECASE))

    async def extract(self, url: str) -> ExtractedProduct:
        product = ExtractedProduct(url=url, source="aliexpress")
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                title_el = soup.find("h1") or soup.find(class_=re.compile(r"title|product-name", re.I))
                if title_el:
                    product.title = title_el.get_text(strip=True)

                # Try to extract from JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            product.title = product.title or data.get("name", "")
                            product.description = product.description or data.get("description", "")
                            product.price = product.price or str(data.get("offers", {}).get("price", ""))
                            imgs = data.get("image", [])
                            if isinstance(imgs, list):
                                product.images.extend(imgs)
                            elif imgs:
                                product.images.append(imgs)
                    except (json.JSONDecodeError, AttributeError):
                        continue

                desc_el = soup.find(class_=re.compile(r"description|detail|product-description", re.I))
                if desc_el:
                    product.description = desc_el.get_text(strip=True)[:5000]

                img_els = soup.find_all("img", class_=re.compile(r"image|img|gallery|thumb", re.I))
                for img in img_els:
                    src = img.get("src") or img.get("data-src") or ""
                    if src and re.match(r"https?://", src):
                        product.images.append(src)

                product.raw_content = soup.get_text()[:10000]
        except Exception as e:
            logger.error("aliexpress_extract_failed", url=url, error=str(e))

        return product

    async def extract_images(self, url: str) -> list[bytes]:
        product = await self.extract(url)
        images = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for img_url in product.images[:10]:
                try:
                    resp = await client.get(img_url)
                    if resp.status_code == 200:
                        images.append(resp.content)
                except Exception:
                    continue
        return images

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
