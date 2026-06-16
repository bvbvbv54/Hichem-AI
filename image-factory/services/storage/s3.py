from __future__ import annotations

import io
from typing import Any, Optional

import boto3
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger
from services.storage.base import StorageBackend, StorageResult

logger = get_logger(__name__)


class S3Storage(StorageBackend):
    """Store images on S3-compatible storage."""

    def __init__(self) -> None:
        self.bucket = settings.storage_s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_s3_endpoint or None,
            aws_access_key_id=settings.storage_s3_access_key,
            aws_secret_access_key=settings.storage_s3_secret_key,
            region_name=settings.storage_s3_region,
        )

    def _build_key(self, job_id: str, filename: str, project_name: str = "") -> str:
        parts = []
        if project_name:
            parts.append(project_name)
        parts.append(job_id)
        parts.append(filename)
        return "/".join(parts)

    async def store(
        self,
        data: bytes,
        job_id: str,
        filename: str,
        project_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StorageResult:
        key = self._build_key(job_id, filename, project_name)

        img = Image.open(io.BytesIO(data))
        w, h = img.size
        mime = f"image/{img.format.lower()}" if img.format else "image/png"

        extra_args = {"ContentType": mime}
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra_args,
        )

        storage_url = f"s3://{self.bucket}/{key}"

        result = StorageResult(
            file_path=key,
            file_size=len(data),
            mime_type=mime,
            width=w,
            height=h,
            storage_url=storage_url,
            metadata=metadata,
        )

        logger.info("file_stored_s3", bucket=self.bucket, key=key, size=len(data))
        return result

    async def retrieve(self, file_path: str) -> Optional[bytes]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=file_path)
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None

    async def delete(self, file_path: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=file_path)
            logger.info("file_deleted_s3", bucket=self.bucket, key=file_path)
            return True
        except Exception:
            return False

    async def exists(self, file_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=file_path)
            return True
        except Exception:
            return False
