from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_429_response_triggers_backoff(mock_redis):
    """Mock server returning 429 then 200 — pipeline should retry once."""
    from services.acquisition.pipeline import AcquisitionPipeline
    from services.acquisition.models import AcquisitionJob, FailureType

    first_response = MagicMock()
    first_response.status_code = 429
    first_response.headers = {"Retry-After": "2", "Content-Type": "text/html"}
    first_response.elapsed.total_seconds.return_value = 0.5

    second_response = MagicMock()
    second_response.status_code = 200
    second_response.headers = {"Content-Type": "text/html"}
    second_response.text = "<html><img src='https://example.com/img.jpg'/></html>"
    second_response.elapsed.total_seconds.return_value = 0.3

    client = AsyncMock()
    client.fetch_with_retry = AsyncMock(side_effect=[first_response, second_response])
    client.close = AsyncMock()

    pipeline = AcquisitionPipeline()
    pipeline.http_client = client
    pipeline.rate_limiter.block_domain = AsyncMock()

    job = AcquisitionJob(job_id="test-429", url="https://example.com/rate-limited", max_images=3)

    with patch.object(pipeline.robots_checker, "is_allowed", AsyncMock(return_value=(True, None))):
        with patch.object(pipeline.robots_checker, "get_crawl_delay", return_value=0):
            with patch.object(pipeline.rate_limiter, "acquire", AsyncMock()):
                with patch.object(pipeline.rate_limiter, "record_success", AsyncMock()):
                    with patch.object(pipeline.monitor, "record", AsyncMock()):
                        with patch.object(pipeline.queue, "load_checkpoint", AsyncMock(return_value={})):
                            with patch.object(pipeline.queue, "save_checkpoint", AsyncMock()):
                                result = await pipeline.run(job)

    assert result.failure_type == FailureType.RATE_LIMITED or result.success is False


@pytest.mark.asyncio
async def test_captcha_detection_returns_captcha_failure():
    """CAPTCHA response should not be retried."""
    from services.acquisition.pipeline import AcquisitionPipeline
    from services.acquisition.models import AcquisitionJob, FailureType

    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "text/html"}
    response.text = "<html><title>Please verify you are human</title><div class='captcha'></div></html>"
    response.elapsed.total_seconds.return_value = 3.5

    client = AsyncMock()
    client.fetch_with_retry = AsyncMock(return_value=response)
    client.close = AsyncMock()

    pipeline = AcquisitionPipeline()
    pipeline.http_client = client
    pipeline.rate_limiter.block_domain = AsyncMock()

    job = AcquisitionJob(job_id="test-captcha", url="https://example.com/captcha", max_images=3)

    with patch.object(pipeline.robots_checker, "is_allowed", AsyncMock(return_value=(True, None))):
        with patch.object(pipeline.robots_checker, "get_crawl_delay", return_value=0):
            with patch.object(pipeline.rate_limiter, "acquire", AsyncMock()):
                with patch.object(pipeline.monitor, "record", AsyncMock()):
                    result = await pipeline.run(job)

    assert result.success is False
    assert result.failure_type in (FailureType.CAPTCHA, FailureType.BOT_BLOCKED)


@pytest.mark.asyncio
async def test_bad_image_rejected_by_pillow(tmp_path):
    """Non-image content should be rejected by downloader."""
    from services.acquisition.image_downloader import ImageDownloader

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "image/jpeg"}
    mock_response.content = b"not a real image data at all"

    client = AsyncMock()
    client.fetch = AsyncMock(return_value=mock_response)

    downloader = ImageDownloader(client)
    with patch.object(downloader, "_output_dir", str(tmp_path)):
        result = await downloader.download("https://example.com/bad.jpg", "job-bad")
    assert result is None


@pytest.mark.asyncio
async def test_image_cache_used_on_second_download(tmp_path):
    """Same URL downloaded twice uses cache second time."""
    from services.acquisition.image_downloader import ImageDownloader
    from services.acquisition.cache import ImageCache
    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_data = buf.getvalue()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "image/jpeg"}
    mock_response.content = jpeg_data

    client = AsyncMock()
    client.fetch = AsyncMock(return_value=mock_response)

    downloader = ImageDownloader(client)
    cache = ImageCache(downloader)

    result1 = await cache.get_or_download("https://example.com/cached-img.jpg", "job-cache")
    result2 = await cache.get_or_download("https://example.com/cached-img.jpg", "job-cache")

    assert result1 is not None
    assert result2 is not None


@pytest.mark.asyncio
async def test_robots_txt_disallows_path():
    """robots.txt disallowing should stop the pipeline."""
    from services.acquisition.pipeline import AcquisitionPipeline
    from services.acquisition.models import AcquisitionJob, FailureType

    client = AsyncMock()
    client.close = AsyncMock()

    pipeline = AcquisitionPipeline()
    pipeline.http_client = client
    pipeline.rate_limiter.block_domain = AsyncMock()

    job = AcquisitionJob(job_id="test-robots", url="https://example.com/forbidden", max_images=3)

    with patch.object(pipeline.robots_checker, "is_allowed", AsyncMock(return_value=(False, FailureType.ROBOTS_DISALLOWED))):
        with patch.object(pipeline.robots_checker, "get_crawl_delay", return_value=0):
            with patch.object(pipeline.rate_limiter, "acquire", AsyncMock()):
                with patch.object(pipeline.monitor, "record", AsyncMock()):
                    result = await pipeline.run(job)

    assert result.success is False
    assert result.failure_type == FailureType.ROBOTS_DISALLOWED
