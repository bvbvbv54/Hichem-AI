from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class StorageResult:
    file_path: str
    file_size: int
    mime_type: str
    width: int
    height: int
    storage_url: str = ""
    metadata: dict[str, Any] | None = None


class StorageBackend(ABC):
    """Abstract base for storage backends."""

    @abstractmethod
    async def store(
        self,
        data: bytes,
        job_id: str,
        filename: str,
        project_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> StorageResult:
        ...

    @abstractmethod
    async def retrieve(self, file_path: str) -> Optional[bytes]:
        ...

    @abstractmethod
    async def delete(self, file_path: str) -> bool:
        ...

    @abstractmethod
    async def exists(self, file_path: str) -> bool:
        ...
