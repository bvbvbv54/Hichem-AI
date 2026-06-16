from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_local_storage_store_and_retrieve():
    from services.storage.local import LocalStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorage(base_path=Path(tmpdir))
        result = await storage.store(
            data=b"test-image-data",
            job_id="test-job",
            filename="test.png",
            project_name="test-project",
        )
        assert result.file_size == 14
        assert "test-job" in result.file_path

        retrieved = await storage.retrieve(result.file_path)
        assert retrieved == b"test-image-data"

        exists = await storage.exists(result.file_path)
        assert exists is True

        deleted = await storage.delete(result.file_path)
        assert deleted is True

        exists_after = await storage.exists(result.file_path)
        assert exists_after is False


@pytest.mark.asyncio
async def test_local_delivery():
    from services.delivery.local import LocalDelivery

    with tempfile.TemporaryDirectory() as tmpdir:
        delivery = LocalDelivery(base_path=Path(tmpdir))
        result = await delivery.deliver(
            data=b"test-image-data",
            filename="test.png",
            asset_id="asset-1",
            job_id="job-1",
            project_name="test",
        )
        assert result.success is True
        assert result.asset_id == "asset-1"


@pytest.mark.asyncio
async def test_storage_backend_selection():
    from services.storage.local import get_storage_backend
    from configs.settings import settings

    settings.storage_backend = "local"
    backend = get_storage_backend()
    from services.storage.local import LocalStorage
    assert isinstance(backend, LocalStorage)


@pytest.mark.asyncio
async def test_delivery_backend_creation():
    from services.delivery.local import create_delivery_backends
    from configs.settings import settings

    settings.delivery_backends = "local"
    backends = create_delivery_backends()
    assert len(backends) == 1
    from services.delivery.local import LocalDelivery
    assert isinstance(backends[0], LocalDelivery)
