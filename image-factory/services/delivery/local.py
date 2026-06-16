from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

import aiofiles
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger
from services.delivery.base import DeliveryBackend, DeliveryResult

logger = get_logger(__name__)


class LocalDelivery(DeliveryBackend):
    """Deliver assets to a local folder."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or settings.delivery_path

    def _build_delivery_path(self, job_id: str, filename: str, project_name: str = "") -> Path:
        parts = [self.base_path, "delivery"]
        if project_name:
            parts.append(project_name)
        parts.append(job_id)
        parts.append(filename)
        return Path(*parts)

    async def deliver(
        self,
        data: bytes,
        filename: str,
        asset_id: str,
        job_id: str,
        project_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> DeliveryResult:
        dest_path = self._build_delivery_path(job_id, filename, project_name)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(str(dest_path), "wb") as f:
            await f.write(data)

        logger.info("delivered_local", path=str(dest_path), asset_id=asset_id)

        return DeliveryResult(
            success=True,
            destination=str(dest_path),
            asset_id=asset_id,
            url=str(dest_path),
            metadata={"local_path": str(dest_path)},
        )

    async def check_health(self) -> bool:
        return self.base_path.exists() if self.base_path else True


def create_delivery_backends() -> list[DeliveryBackend]:
    backends: list[DeliveryBackend] = []
    for backend_name in settings.delivery_backend_list:
        if backend_name == "local":
            backends.append(LocalDelivery())
        elif backend_name == "s3":
            from services.delivery.s3 import S3Delivery
            backends.append(S3Delivery())
        elif backend_name == "webhook":
            from services.delivery.webhook import WebhookDelivery
            backends.append(WebhookDelivery())
    if not backends:
        backends.append(LocalDelivery())
    return backends
