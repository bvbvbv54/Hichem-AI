from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_downloader_rejects_non_image():
    from services.acquisition.image_downloader import ImageDownloader
    from services.acquisition.http_client import HardenedHTTPClient

    mock_client = MagicMock(spec=HardenedHTTPClient)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = b"<html>not an image</html>"
    mock_client.get = AsyncMock(return_value=mock_response)

    downloader = ImageDownloader(mock_client)
    path, mime = await downloader.download("https://example.com/fake.jpg", "job1")
    assert path is None


@pytest.mark.asyncio
async def test_downloader_rejects_too_small():
    from services.acquisition.image_downloader import ImageDownloader
    from services.acquisition.http_client import HardenedHTTPClient

    mock_client = MagicMock(spec=HardenedHTTPClient)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "image/jpeg"}
    mock_response.content = b"\xff\xd8\xff\xe0" * 100
    mock_client.get = AsyncMock(return_value=mock_response)

    downloader = ImageDownloader(mock_client)
    path, mime = await downloader.download("https://example.com/small.jpg", "job1")
    assert path is None


@pytest.mark.asyncio
async def test_downloader_returns_path_on_success(tmp_path):
    from services.acquisition.image_downloader import ImageDownloader
    from services.acquisition.http_client import HardenedHTTPClient

    from PIL import Image
    import io
    img = Image.new("RGB", (800, 800), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    jpeg_data = buf.getvalue()

    mock_client = MagicMock(spec=HardenedHTTPClient)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "image/jpeg"}
    mock_response.content = jpeg_data
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.acquisition.image_downloader.settings") as mock_settings:
        mock_settings.storage_path = str(tmp_path)
        downloader = ImageDownloader(mock_client)
        path, mime = await downloader.download("https://example.com/real.jpg", "job1")
        assert path is not None


@pytest.mark.asyncio
async def test_downloader_handles_404():
    from services.acquisition.image_downloader import ImageDownloader
    from services.acquisition.http_client import HardenedHTTPClient

    mock_client = MagicMock(spec=HardenedHTTPClient)
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_client.get = AsyncMock(return_value=mock_response)

    downloader = ImageDownloader(mock_client)
    path, mime = await downloader.download("https://example.com/missing.jpg", "job1")
    assert path is None
