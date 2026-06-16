from __future__ import annotations

from typing import Any, Optional

from configs.logging import get_logger
from services.extractor.parsers.base import BaseParser, ExtractedProduct
from services.extractor.parsers.alibaba import AlibabaParser
from services.extractor.parsers.aliexpress import AliExpressParser
from services.extractor.parsers.generic import GenericParser

logger = get_logger(__name__)


class ProductExtractor:
    """
    Orchestrates product data extraction from supplier URLs.
    Uses the Chain of Responsibility pattern to find the right parser.
    """

    def __init__(self) -> None:
        self.parsers: list[BaseParser] = [
            AlibabaParser(),
            AliExpressParser(),
            GenericParser(),
        ]

    def _find_parser(self, url: str) -> Optional[BaseParser]:
        for parser in self.parsers:
            if parser.can_handle(url):
                return parser
        return None

    async def extract_url(self, url: str) -> ExtractedProduct:
        parser = self._find_parser(url)
        if not parser:
            logger.warning("no_parser_found", url=url)
            return ExtractedProduct(url=url, source="unknown")
        logger.info("extracting_product", url=url, parser=parser.__class__.__name__)
        return await parser.extract(url)

    async def extract_images(self, url: str) -> list[bytes]:
        parser = self._find_parser(url)
        if not parser:
            return []
        return await parser.extract_images(url)

    async def process_row(
        self,
        row: dict[str, Any],
        default_language: str = "en",
    ) -> dict[str, Any]:
        url = row.get("product_url", row.get("url", ""))
        result: dict[str, Any] = {
            "row_data": row,
            "extracted": None,
            "images": [],
            "error": None,
        }

        if not url:
            result["error"] = "No URL provided"
            return result

        try:
            extracted = await self.extract_url(url)
            result["extracted"] = {
                "title": extracted.title or row.get("product_title", ""),
                "description": extracted.description or row.get("product_description", ""),
                "category": extracted.category or row.get("product_category", ""),
                "price": extracted.price or row.get("price", ""),
                "images": extracted.images,
                "source": extracted.source,
            }

            if extracted.images:
                result["images"] = await self.extract_images(url)

        except Exception as e:
            logger.error("row_processing_failed", url=url, error=str(e))
            result["error"] = str(e)
            result["extracted"] = {
                "title": row.get("product_title", ""),
                "description": row.get("product_description", ""),
                "category": row.get("product_category", ""),
            }

        return result
