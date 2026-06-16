from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExtractedProduct:
    url: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    price: str = ""
    currency: str = ""
    images: list[str] = field(default_factory=list)
    specifications: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    raw_content: str = ""


class BaseParser(ABC):
    """Abstract base for supplier-specific parsers."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this parser can handle the given URL."""
        ...

    @abstractmethod
    async def extract(self, url: str) -> ExtractedProduct:
        """Extract product information from the URL."""
        ...

    @abstractmethod
    async def extract_images(self, url: str) -> list[bytes]:
        """Download product images from the URL."""
        ...
