from __future__ import annotations

import traceback

from workers.celery_app import celery_app
from workers.async_runner import run_async
from configs.settings import settings
from configs.logging import get_logger
from database.session import async_session
from database.repository import AssetRepository

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def deliver_asset(self, asset_id: str):
    """Deliver a single asset to all configured backends."""
    logger.info("delivering_asset", asset_id=asset_id)
    try:
        run_async(_execute_delivery(asset_id))
    except Exception as exc:
        logger.error("delivery_failed", asset_id=asset_id, error=str(exc))
        run_async(_update_delivery_status(asset_id, "failed"))
        raise self.retry(exc=exc)


async def _execute_delivery(asset_id: str):
    async with async_session() as session:
        asset_repo = AssetRepository(session)
        asset = await asset_repo.get(asset_id)
        if not asset:
            logger.error("asset_not_found", asset_id=asset_id)
            return

        from services.storage.local import LocalStorage
        storage = LocalStorage()
        asset_data = await storage.retrieve(asset.file_path)

        if not asset_data:
            logger.error("asset_data_not_found", path=asset.file_path)
            return

        from services.delivery.local import create_delivery_backends
        backends = create_delivery_backends()

        for backend in backends:
            try:
                result = await backend.deliver(
                    data=asset_data,
                    filename=asset.filename,
                    asset_id=asset.id,
                    job_id=asset.job_id,
                    project_name="",
                )
                if not result.success:
                    logger.error("backend_delivery_failed", backend=type(backend).__name__, error=result.error_message)
            except Exception as e:
                logger.error("backend_delivery_error", backend=type(backend).__name__, error=str(e))

        await asset_repo.update(asset_id, {"delivery_status": "delivered"})


async def _update_delivery_status(asset_id: str, status: str):
    async with async_session() as session:
        asset_repo = AssetRepository(session)
        await asset_repo.update(asset_id, {"delivery_status": status})
