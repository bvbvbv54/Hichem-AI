from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DeliveryResult:
    success: bool
    destination: str
    asset_id: str
    url: str = ""
    error_message: str = ""
    metadata: dict[str, Any] | None = None


class DeliveryBackend(ABC):
    """Abstract base for delivery backends."""

    @abstractmethod
    async def deliver(
        self,
        data: bytes,
        filename: str,
        asset_id: str,
        job_id: str,
        project_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> DeliveryResult:
        ...

    @abstractmethod
    async def check_health(self) -> bool:
        ...
