from __future__ import annotations

import sys
import types

# Mock google modules before any service imports trigger them
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

# Mock google modules before any service imports trigger them
class _MockGenerativeModel:
    def generate_content(self, *a, **kw):
        return MagicMock(text="mocked response")

    def __call__(self, *a, **kw):
        return self

class _MockGenAI:
    def configure(self, **kw):
        pass
    def GenerativeModel(self, *a, **kw):
        return _MockGenerativeModel()
    def GenerationConfig(self, **kw):
        return kw

gemini_mock = types.ModuleType("google.generativeai")
mock_genai = _MockGenAI()
gemini_mock.__dict__["configure"] = mock_genai.configure
gemini_mock.__dict__["GenerativeModel"] = mock_genai.GenerativeModel
gemini_mock.__dict__["GenerationConfig"] = mock_genai.GenerationConfig
sys.modules["google.generativeai"] = gemini_mock

# Also mock google.api_core for Gemini client retry decorator
api_core = types.ModuleType("google.api_core")
api_core.exceptions = types.ModuleType("google.api_core.exceptions")
api_core.exceptions.ResourceExhausted = Exception
api_core.exceptions.ServiceUnavailable = Exception
api_core.exceptions.DeadlineExceeded = Exception
sys.modules["google.api_core"] = api_core
sys.modules["google.api_core.exceptions"] = api_core.exceptions

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
    settings.gemini_api_key = "test-gemini-key"
    settings.storage_backend = "local"
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
def mock_gemini():
    """Mock GeminiClient for pipeline tests."""
    with patch("services.gemini.client.GeminiClient") as mock:
        client = MagicMock()
        client.generate_text = AsyncMock(return_value="A beautiful product image with premium lighting.")
        client.generate_with_images = AsyncMock(return_value=(
            "Product name: Test Product\nMaterial: Leather\nDimensions: 10x10x5cm",
            {"product_name": "Test Product", "material": "Leather", "dimensions": "10x10x5cm"},
        ))
        mock.return_value = client
        yield client


@pytest.fixture
def mock_gemini_singleton():
    """Mock the gemini_client singleton used across pipeline stages."""
    with patch("services.pipeline.stage1_analyzer.gemini_client") as mock:
        mock.generate_with_images = AsyncMock(return_value=(
            '{"product_name":"Test","material":"Plastic","dimensions":"5x5x5","logo":"none","translated_labels":[],"key_visual_features":["red"],"background_color":"white","primary_colors":["red"],"detected_language":"en"}',
            {},
        ))
        yield mock


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
