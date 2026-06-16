from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_generation_request_model():
    from services.nano_banana.models import GenerationRequest, GenerationResult

    req = GenerationRequest(prompt="Test", num_images=2)
    assert req.prompt == "Test"
    assert req.num_images == 2
    assert req.width == 1024

    result = GenerationResult(image_data=b"test", width=512, height=512)
    assert result.mime_type == "image/png"
    assert result.width == 512


@pytest.mark.asyncio
async def test_provider_selection():
    from services.nano_banana.client import NanoBananaClient

    with patch("configs.settings.settings.image_provider", "replicate"):
        client = NanoBananaClient()
        assert client.provider is not None


@pytest.mark.asyncio
async def test_generate_with_mock():
    from services.nano_banana.client import NanoBananaClient
    from services.nano_banana.models import GenerationRequest, GenerationResult

    mock_provider = AsyncMock()
    mock_provider.generate.return_value = [
        GenerationResult(image_data=b"test-image-data", width=1024, height=1024)
    ]

    client = NanoBananaClient()
    client.provider = mock_provider

    req = GenerationRequest(prompt="Test prompt")
    results = await client.generate(req)

    assert len(results) == 1
    assert results[0].image_data == b"test-image-data"
    assert mock_provider.generate.called
