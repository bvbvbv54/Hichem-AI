from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from configs.settings import settings


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def test_settings():
    """Reset to test settings for every test."""
    settings.app_env = "test"
    settings.api_key = "test-api-key"
    settings.storage_local_path = "./test-outputs"
    settings.delivery_backends = "local"
    settings.delivery_local_path = "./test-outputs"
    settings.google_drive_auto_upload = False
    settings.batch_max_concurrent = 3
    yield


@pytest.fixture
def fixture_path() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_xlsx(fixture_path: Path) -> bytes:
    return (fixture_path / "sample_products.xlsx").read_bytes()


@pytest.fixture
def sample_csv(fixture_path: Path) -> bytes:
    return b"URL,Product Name,Priority,Category,Notes\nhttps://example.com/a,Alpha,1,Books,\nhttps://example.com/b,Beta,2,Music,\n"


@pytest.fixture
def clean_test_image(fixture_path: Path) -> bytes:
    return (fixture_path / "clean_product_image.jpg").read_bytes()


@pytest.fixture
def chinese_test_image(fixture_path: Path) -> bytes:
    return (fixture_path / "chinese_product_image.jpg").read_bytes()


@pytest.fixture
def sample_batch_json(fixture_path: Path) -> list[dict]:
    import json
    return json.loads((fixture_path / "sample_batch.json").read_text())


@pytest.fixture
def mock_nano_banana():
    """Mock Nano Banana client."""
    with patch("services.nano_banana.client.NanoBananaClient") as mock:
        client = MagicMock()
        from services.nano_banana.models import GenerationResult
        client.generate = AsyncMock(return_value=[
            GenerationResult(image_data=b"fake-image-data", width=1024, height=1024, mime_type="image/png"),
        ])
        client.generate_image_to_image = AsyncMock(return_value=[
            GenerationResult(image_data=b"fake-img2img-data", width=1024, height=1024, mime_type="image/png"),
        ])
        mock.return_value = client
        yield client


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("redis.asyncio.from_url") as mock:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=True)
        redis.lpush = AsyncMock(return_value=1)
        redis.ltrim = AsyncMock(return_value=True)
        redis.expire = AsyncMock(return_value=True)
        redis.lrange = AsyncMock(return_value=[])
        redis.hincrby = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value={})
        redis.ping = AsyncMock(return_value=True)
        redis.publish = AsyncMock(return_value=1)
        redis.aclose = AsyncMock(return_value=None)
        mock.return_value = redis
        yield redis


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, Any]:
    """Create async test client."""
    from api.app import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def api_headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}
