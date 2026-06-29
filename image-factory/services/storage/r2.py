from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

R2_ACCOUNT_ID = "1594a155d6f247883b97fd9e3743cda7"
R2_ACCESS_KEY = "c1b65a111faf81d7772def8a25740dd0"
R2_SECRET_KEY = "a4f37928772790e8c186931a159016bd1e735a3035f5fafd9c1f82dd6436cdc2"
R2_BUCKET = "imagefactory"
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
R2_ENABLED = True


_R2_CLIENT = None


def _get_client():
    global _R2_CLIENT
    if _R2_CLIENT is not None:
        return _R2_CLIENT
    import boto3
    from botocore.config import Config as BotoConfig
    client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4", max_pool_connections=10),
    )
    _R2_CLIENT = client
    return client


class R2Storage:
    def __init__(self):
        self._client = _get_client()

    def _make_key(self, project_id: str, product_id: str, category: str, filename: str) -> str:
        return f"{project_id}/{product_id}/{category}/{filename}"

    def _public_url(self, key: str) -> str:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": R2_BUCKET, "Key": key},
            ExpiresIn=86400 * 7,
        )
        return url

    async def upload_file(
        self,
        local_path: str | Path,
        project_id: str,
        product_id: str,
        category: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        fname = filename or local.name
        key = self._make_key(project_id, product_id, category, fname)

        if content_type is None:
            content_type, _ = mimetypes.guess_type(fname)
            if content_type is None:
                ext = Path(fname).suffix.lower()
                content_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                }.get(ext, "application/octet-stream")

        def _upload():
            self._client.upload_file(
                str(local),
                R2_BUCKET,
                key,
                ExtraArgs={"ContentType": content_type},
            )

        await asyncio.to_thread(_upload)
        public_url = self._public_url(key)

        logger.info(
            "r2_uploaded",
            key=key,
            bucket=R2_BUCKET,
            size=local.stat().st_size,
            url=public_url,
        )

        return {
            "key": key,
            "url": public_url,
            "bucket": R2_BUCKET,
            "filename": fname,
            "file_size": local.stat().st_size,
        }

    async def upload_directory(
        self,
        local_dir: str | Path,
        project_id: str,
        product_id: str,
        category: str,
    ) -> list[dict[str, Any]]:
        local = Path(local_dir)
        if not local.is_dir():
            logger.warning("r2_upload_dir_not_found", path=str(local))
            return []

        results = []
        for f in sorted(local.iterdir()):
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                result = await self.upload_file(f, project_id, product_id, category)
                results.append(result)
        return results

    async def delete_file(self, key: str) -> bool:
        def _delete():
            self._client.delete_object(Bucket=R2_BUCKET, Key=key)

        try:
            await asyncio.to_thread(_delete)
            logger.info("r2_deleted", key=key)
            return True
        except Exception as e:
            logger.warning("r2_delete_failed", key=key, error=str(e))
            return False

    async def file_exists(self, key: str) -> bool:
        def _head():
            self._client.head_object(Bucket=R2_BUCKET, Key=key)
            return True

        try:
            result = await asyncio.to_thread(_head)
            return result
        except Exception:
            return False

    async def list_files(self, prefix: str) -> list[dict[str, Any]]:
        def _list():
            objects = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=R2_BUCKET, Prefix=prefix):
                for obj in page.get("Contents", []):
                    objects.append(obj)
            return objects

        try:
            objects = await asyncio.to_thread(_list)
            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat() if hasattr(obj["LastModified"], "isoformat") else str(obj["LastModified"]),
                    "url": self._public_url(obj["Key"]),
                }
                for obj in objects
            ]
        except Exception as e:
            logger.warning("r2_list_failed", prefix=prefix, error=str(e))
            return []

    async def download_file(self, key: str, local_path: str | Path) -> Path:
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)

        def _download():
            self._client.download_file(R2_BUCKET, key, str(local))

        await asyncio.to_thread(_download)
        return local


    R2_URL_CACHE_PREFIX = "r2_url_cache:"

    async def register_url_cache(self, image_url: str, r2_key: str) -> None:
        import hashlib
        import json
        import redis.asyncio as redis_async

        url_hash = hashlib.sha256(image_url.encode()).hexdigest()
        cache_key = f"cache/r2_url/{url_hash}.json"
        payload = json.dumps({"r2_key": r2_key, "url": image_url})

        def _upload():
            import io
            self._client.put_object(
                Bucket=R2_BUCKET,
                Key=cache_key,
                Body=payload.encode(),
                ContentType="application/json",
            )

        try:
            await asyncio.to_thread(_upload)
        except Exception as e:
            logger.warning("r2_cache_register_failed", url=image_url, error=str(e))

        try:
            redis_conn = await redis_async.from_url(settings.redis_url)
            await redis_conn.set(f"{self.R2_URL_CACHE_PREFIX}{url_hash}", r2_key)
            await redis_conn.aclose()
        except Exception as e:
            logger.warning("r2_cache_redis_failed", url=image_url, error=str(e))

    async def get_cached_r2_url(self, image_url: str) -> str | None:
        import hashlib
        import json
        import redis.asyncio as redis_async

        url_hash = hashlib.sha256(image_url.encode()).hexdigest()

        try:
            redis_conn = await redis_async.from_url(settings.redis_url)
            r2_key = await redis_conn.get(f"{self.R2_URL_CACHE_PREFIX}{url_hash}")
            if r2_key:
                r2_key = r2_key.decode()
                exists = await self.file_exists(r2_key)
                if exists:
                    await redis_conn.aclose()
                    return self._public_url(r2_key)
            await redis_conn.aclose()
        except Exception:
            pass

        try:
            cache_key = f"cache/r2_url/{url_hash}.json"

            def _get():
                obj = self._client.get_object(Bucket=R2_BUCKET, Key=cache_key)
                return obj["Body"].read().decode()

            payload = await asyncio.to_thread(_get)
            data = json.loads(payload)
            r2_key = data["r2_key"]
            exists = await self.file_exists(r2_key)
            if exists:
                try:
                    redis_conn = await redis_async.from_url(settings.redis_url)
                    await redis_conn.set(f"{self.R2_URL_CACHE_PREFIX}{url_hash}", r2_key)
                    await redis_conn.aclose()
                except Exception:
                    pass
                return self._public_url(r2_key)
        except Exception:
            pass

        return None


_r2_storage: R2Storage | None = None


def get_r2_storage() -> R2Storage:
    global _r2_storage
    if _r2_storage is None:
        _r2_storage = R2Storage()
    return _r2_storage
