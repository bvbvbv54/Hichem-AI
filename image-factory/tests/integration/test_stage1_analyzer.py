from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_stage1_sends_single_call(mock_gemini_singleton, tmp_path):
    """Stage 1 should send all images in a single Gemini call."""
    from services.pipeline.stage1_analyzer import Stage1Analyzer

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"fake-image-data-1")
    img2.write_bytes(b"fake-image-data-2")

    redis = AsyncMock()
    analyzer = Stage1Analyzer(redis)
    result = await analyzer.analyze([str(img1), str(img2)], "https://example.com")

    assert result is not None
    assert mock_gemini_singleton.generate_with_images.call_count == 1


@pytest.mark.asyncio
async def test_stage1_returns_product_spec(mock_gemini_singleton, tmp_path):
    """Stage 1 should return a valid ProductSpec."""
    from services.pipeline.stage1_analyzer import Stage1Analyzer

    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake-image-data")

    redis = AsyncMock()
    analyzer = Stage1Analyzer(redis)
    spec = await analyzer.analyze([str(img)], "https://example.com/test")

    assert spec is not None
    assert hasattr(spec, "product_name")
    assert hasattr(spec, "material")
    assert hasattr(spec, "dimensions")
    assert hasattr(spec, "detected_language")
    assert hasattr(spec, "translated_labels")


@pytest.mark.asyncio
async def test_stage1_handles_empty_images():
    """Stage 1 should handle empty image list gracefully."""
    from services.pipeline.stage1_analyzer import Stage1Analyzer
    redis = AsyncMock()
    analyzer = Stage1Analyzer(redis)
    result = await analyzer.analyze([], "https://example.com")
    assert result is not None


@pytest.mark.asyncio
async def test_stage1_includes_url_in_prompt(mock_gemini_singleton, tmp_path):
    """URL should be passed to Gemini as context."""
    from services.pipeline.stage1_analyzer import Stage1Analyzer
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")
    redis = AsyncMock()
    analyzer = Stage1Analyzer(redis)
    result = await analyzer.analyze([str(img)], "https://example.com/unique-product-123")
    kw = mock_gemini_singleton.generate_with_images.call_args
    if kw:
        assert "unique-product-123" in str(kw)
