from __future__ import annotations

import hashlib
from pathlib import Path

import redis.asyncio as redis_async

from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.image_downloader import ImageDownloader
from services.acquisition.http_client import HardenedHTTPClient

logger = get_logger(__name__)

CACHE_PREFIX = "img_cache:"
URL_CACHE_PREFIX = "img_url_cache:"
CACHE_TTL = settings.scraper_cache_ttl_days * 86400


class ImageCache:
    def __init__(self, downloader: ImageDownloader) -> None:
        self.downloader = downloader
        self._redis: redis_async.Redis | None = None

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    async def get_or_download(self, url: str, job_id: str) -> tuple[str | None, bool]:
        redis_conn = await self._get_redis()
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        content_hash = await redis_conn.get(f"{URL_CACHE_PREFIX}{url_hash}")
        if content_hash:
            sha_key = content_hash.decode()
            cached_path = await redis_conn.get(f"{CACHE_PREFIX}{sha_key}")
            if cached_path:
                path_str = cached_path.decode()
                if Path(path_str).exists():
                    logger.info("cache_hit", url=url, path=path_str)
                    return path_str, True
                logger.info("cache_stale_file_missing", url=url, path=path_str)
        local_path, sha256 = await self.downloader.download(url, job_id)
        if local_path and sha256:
            await redis_conn.setex(f"{URL_CACHE_PREFIX}{url_hash}", CACHE_TTL, sha256)
            await redis_conn.setex(f"{CACHE_PREFIX}{sha256}", CACHE_TTL, local_path)
            return local_path, False
        return None, False

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
