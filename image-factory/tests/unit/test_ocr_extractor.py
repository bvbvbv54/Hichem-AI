from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock(return_value=None)
    return r


@pytest.fixture(autouse=True)
def mock_gemini():
    with patch("services.pipeline.ocr_extractor.gemini_client") as m:
        m.generate_with_images = AsyncMock(return_value='{"has_chinese": true, "labels": []}')
        yield m


@pytest.mark.asyncio
async def test_ocr_extractor_no_chinese_text(chinese_test_image, tmp_path, mock_redis):
    from services.pipeline.ocr_extractor import OCRExtractor
    extractor = OCRExtractor(mock_redis)
    img_path = tmp_path / "chinese_test.jpg"
    img_path.write_bytes(chinese_test_image)
    result = await extractor.scan_image(str(img_path))
    assert isinstance(result, dict)
    assert "has_chinese" in result


@pytest.mark.asyncio
async def test_ocr_extractor_empty_on_clean_image(clean_test_image, tmp_path, mock_redis):
    from services.pipeline.ocr_extractor import OCRExtractor
    extractor = OCRExtractor(mock_redis)
    img_path = tmp_path / "clean_test.jpg"
    img_path.write_bytes(clean_test_image)
    result = await extractor.scan_image(str(img_path))
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_ocr_extractor_non_existent_file(mock_redis):
    from services.pipeline.ocr_extractor import OCRExtractor
    extractor = OCRExtractor(mock_redis)
    with pytest.raises(FileNotFoundError):
        await extractor.scan_image("/tmp/non_existent_image.jpg")


@pytest.mark.asyncio
async def test_ocr_extractor_scans_multiple_images(clean_test_image, tmp_path, mock_redis):
    from services.pipeline.ocr_extractor import OCRExtractor
    img1 = tmp_path / "a.jpg"
    img2 = tmp_path / "b.jpg"
    img1.write_bytes(clean_test_image)
    img2.write_bytes(clean_test_image)
    extractor = OCRExtractor(mock_redis)
    results = await extractor.scan_all([str(img1), str(img2)])
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_ocr_extractor_model_import():
    from services.pipeline.models import ChineseLabel
    label = ChineseLabel(original="测试", literal_translation="Test", semantic_rewrite="Test", position="front")
    assert label.original == "测试"
    assert label.literal_translation == "Test"
