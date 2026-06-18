from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import aiofiles
import redis.asyncio as redis_async
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.http_client import HardenedHTTPClient

logger = get_logger(__name__)

VALID_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}

MIN_SIZE = int(settings.scraper_min_image_size_kb * 1024)
MAX_SIZE = 50 * 1024 * 1024

GLOBAL_HASH_SET = "global_content_hashes"
GLOBAL_HASH_PATH_PREFIX = "global_hash_path:"


class ImageDownloader:
    def __init__(self, http_client: HardenedHTTPClient) -> None:
        self.http_client = http_client
        self._redis: redis_async.Redis | None = None

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def download(self, url: str, job_id: str) -> tuple[str | None, str | None]:
        try:
            redis_conn = await self._get_redis()
            response = await self.http_client.get(url)
            if response.status_code != 200:
                logger.warning("download_failed", url=url, status=response.status_code)
                return None, None
            data = response.content
            if len(data) < MIN_SIZE:
                logger.warning("image_too_small", url=url, size=len(data))
                return None, None
            if len(data) > MAX_SIZE:
                logger.warning("image_too_large", url=url, size=len(data))
                return None, None
            mime = response.headers.get("content-type", "").lower().split(";")[0].strip()
            if mime and mime not in VALID_MIME_TYPES:
                logger.warning("invalid_mime_type", url=url, mime=mime)
                return None, None
            try:
                img = Image.open(io.BytesIO(data))
                img.verify()
                img = Image.open(io.BytesIO(data))
                img.load()
                if img.width < 200 or img.height < 200:
                    logger.warning("image_too_small_dimensions", url=url, dims=(img.width, img.height))
                    return None, None
            except Exception as exc:
                logger.warning("image_verification_failed", url=url, error=str(exc))
                return None, None

            sha256 = hashlib.sha256(data).hexdigest()
            ext = _ext_from_mime(mime)

            is_dup = await redis_conn.sismember(GLOBAL_HASH_SET, sha256)
            if is_dup:
                existing_path = await redis_conn.get(f"{GLOBAL_HASH_PATH_PREFIX}{sha256}")
                if existing_path:
                    path_str = existing_path.decode()
                    if Path(path_str).exists():
                        logger.info("global_duplicate_skipped", url=url, sha256=sha256, path=path_str)
                        return path_str, sha256
                logger.info("global_duplicate_no_file", url=url, sha256=sha256)

            out_dir = Path(settings.storage_path) / "raw_images"
            out_dir.mkdir(parents=True, exist_ok=True)
            file_path = out_dir / f"{sha256}{ext}"

            if not file_path.exists():
                async with aiofiles.open(str(file_path), "wb") as f:
                    await f.write(data)
                logger.info("image_downloaded", url=url, path=str(file_path), size=len(data))
            else:
                logger.info("image_already_exists", url=url, path=str(file_path))

            await redis_conn.sadd(GLOBAL_HASH_SET, sha256)
            await redis_conn.set(f"{GLOBAL_HASH_PATH_PREFIX}{sha256}", str(file_path))

            return str(file_path), sha256
        except Exception as exc:
            logger.error("download_exception", url=url, error=str(exc))
            return None, None

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


def _ext_from_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
    }.get(mime, ".jpg")
