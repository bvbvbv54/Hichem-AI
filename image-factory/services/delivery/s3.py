from __future__ import annotations

import io
from typing import Any, Optional

import boto3
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger
from services.delivery.base import DeliveryBackend, DeliveryResult

logger = get_logger(__name__)


class S3Delivery(DeliveryBackend):
    """Deliver assets to S3-compatible storage."""

    def __init__(self) -> None:
        self.bucket = settings.delivery_s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.delivery_s3_endpoint or None,
            aws_access_key_id=settings.delivery_s3_access_key,
            aws_secret_access_key=settings.delivery_s3_secret_key,
            region_name=settings.delivery_s3_region,
        )

    def _build_key(self, job_id: str, filename: str, project_name: str = "") -> str:
        parts = ["delivery"]
        if project_name:
            parts.append(project_name)
        parts.append(job_id)
        parts.append(filename)
        return "/".join(parts)

    async def deliver(
        self,
        data: bytes,
        filename: str,
        asset_id: str,
        job_id: str,
        project_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> DeliveryResult:
        key = self._build_key(job_id, filename, project_name)

        img = Image.open(io.BytesIO(data))
        mime = f"image/{img.format.lower()}" if img.format else "image/png"

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=mime,
        )

        url = f"s3://{self.bucket}/{key}"
        logger.info("delivered_s3", bucket=self.bucket, key=key, asset_id=asset_id)

        return DeliveryResult(
            success=True,
            destination=f"s3://{self.bucket}/{key}",
            asset_id=asset_id,
            url=url,
            metadata={"bucket": self.bucket, "key": key},
        )

    async def check_health(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False
