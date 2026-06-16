from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

import aiofiles
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger
from services.storage.base import StorageBackend, StorageResult

logger = get_logger(__name__)


class LocalStorage(StorageBackend):
    """Store images on the local filesystem."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or settings.storage_path

    def _build_path(self, job_id: str, filename: str, project_name: str = "") -> Path:
        parts = [self.base_path]
        if project_name:
            parts.append(project_name)
        parts.append(job_id)
        parts.append(filename)
        return Path(*parts)

    async def store(
        self,
        data: bytes,
        job_id: str,
        filename: str,
        project_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StorageResult:
        file_path = self._build_path(job_id, filename, project_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(str(file_path), "wb") as f:
            await f.write(data)

        # Get image dimensions
        img = Image.open(io.BytesIO(data))
        w, h = img.size

        result = StorageResult(
            file_path=str(file_path),
            file_size=len(data),
            mime_type=f"image/{img.format.lower()}" if img.format else "image/png",
            width=w,
            height=h,
            storage_url=str(file_path),
            metadata=metadata,
        )

        logger.info("file_stored", path=str(file_path), size=len(data))
        return result

    async def retrieve(self, file_path: str) -> Optional[bytes]:
        path = Path(file_path)
        if not path.exists():
            return None
        async with aiofiles.open(str(path), "rb") as f:
            return await f.read()

    async def delete(self, file_path: str) -> bool:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info("file_deleted", path=file_path)
            return True
        return False

    async def exists(self, file_path: str) -> bool:
        return Path(file_path).exists()


def get_storage_backend() -> StorageBackend:
    if settings.storage_backend == "s3":
        from services.storage.s3 import S3Storage
        return S3Storage()
    return LocalStorage()
