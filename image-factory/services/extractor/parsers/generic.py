from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from configs.logging import get_logger
from services.extractor.parsers.base import BaseParser, ExtractedProduct

logger = get_logger(__name__)


class GenericParser(BaseParser):
    """Generic parser for any supplier website."""

    def can_handle(self, url: str) -> bool:
        return bool(re.match(r"https?://", url))

    async def extract(self, url: str) -> ExtractedProduct:
        product = ExtractedProduct(url=url, source="generic")
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                title_el = (
                    soup.find("h1")
                    or soup.find("meta", attrs={"property": "og:title"})
                    or soup.find("meta", attrs={"name": "twitter:title"})
                )
                if title_el:
                    if title_el.name == "meta":
                        product.title = title_el.get("content", "")
                    else:
                        product.title = title_el.get_text(strip=True)

                desc_el = (
                    soup.find("meta", attrs={"name": "description"})
                    or soup.find("meta", attrs={"property": "og:description"})
                )
                if desc_el:
                    product.description = desc_el.get("content", "")[:5000]

                img_el = soup.find("meta", attrs={"property": "og:image"})
                if img_el and img_el.get("content"):
                    product.images.append(img_el["content"])

                price_el = soup.find(class_=re.compile(r"price", re.I)) or soup.find(attrs={"data-price": True})
                if price_el:
                    product.price = price_el.get_text(strip=True) if hasattr(price_el, "get_text") else str(price_el)

                product.raw_content = soup.get_text()[:10000]
        except Exception as e:
            logger.error("generic_extract_failed", url=url, error=str(e))

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
