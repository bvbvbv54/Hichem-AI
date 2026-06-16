from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

import httpx

from configs.settings import settings
from configs.logging import get_logger
from services.delivery.base import DeliveryBackend, DeliveryResult

logger = get_logger(__name__)


class WebhookDelivery(DeliveryBackend):
    """Deliver assets via webhook callbacks."""

    def __init__(self) -> None:
        self.webhook_url = settings.delivery_webhook_url
        self.webhook_secret = settings.delivery_webhook_secret

    async def deliver(
        self,
        data: bytes,
        filename: str,
        asset_id: str,
        job_id: str,
        project_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> DeliveryResult:
        if not self.webhook_url:
            return DeliveryResult(
                success=False,
                destination="webhook",
                asset_id=asset_id,
                error_message="No webhook URL configured",
            )

        import base64
        payload = {
            "asset_id": asset_id,
            "job_id": job_id,
            "filename": filename,
            "project_name": project_name,
            "data_base64": base64.b64encode(data).decode("utf-8"),
            "metadata": metadata or {},
        }

        body = json.dumps(payload)
        signature = hmac.new(
            self.webhook_secret.encode() if self.webhook_secret else b"",
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.webhook_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Asset-ID": asset_id,
                    },
                )
                response.raise_for_status()

            logger.info("delivered_webhook", url=self.webhook_url, asset_id=asset_id)
            return DeliveryResult(
                success=True,
                destination=self.webhook_url,
                asset_id=asset_id,
                url=self.webhook_url,
            )

        except Exception as e:
            logger.error("webhook_delivery_failed", url=self.webhook_url, error=str(e))
            return DeliveryResult(
                success=False,
                destination=self.webhook_url,
                asset_id=asset_id,
                error_message=str(e),
            )

    async def check_health(self) -> bool:
        return bool(self.webhook_url)
