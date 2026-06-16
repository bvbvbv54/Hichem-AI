from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as redis_async
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_CACHE_PREFIX = "gdrive:folder:"
FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveManager:
    def __init__(self) -> None:
        self._credentials_path = Path(settings.google_drive_credentials_path)
        self._token_path = Path(settings.google_drive_token_path)
        self._creds: Credentials | None = None
        self._service: Any = None
        self._redis: redis_async.Redis | None = None

    async def _get_redis(self) -> redis_async.Redis:
        if self._redis is None:
            self._redis = await redis_async.from_url(settings.redis_url)
        return self._redis

    @property
    def is_authenticated(self) -> bool:
        return self._creds is not None and self._creds.valid

    async def authenticate(self) -> bool:
        creds = None
        if self._token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)
            except Exception as e:
                logger.warning("token_load_failed", error=str(e))
        if creds and creds.expired and creds.refresh_token:
            creds = await asyncio.to_thread(creds.refresh, Request())
        self._creds = creds
        if creds and creds.valid:
            self._service = await asyncio.to_thread(build, "drive", "v3", credentials=creds)
            return True
        return False

    def get_auth_url(self) -> str:
        flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
        return auth_url

    async def handle_callback(self, code: str) -> dict:
        flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        creds = await asyncio.to_thread(flow.fetch_token, code=code)
        self._creds = creds
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        self._service = await asyncio.to_thread(build, "drive", "v3", credentials=creds)
        about = await asyncio.to_thread(self._service.about().get(fields="user").execute)
        email = about.get("user", {}).get("emailAddress", "unknown")
        return {
            "authenticated": True,
            "email": email,
            "token_path": str(self._token_path),
        }

    async def get_or_create_folder(self, folder_name: str, parent_id: str | None = None) -> str:
        redis_conn = await self._get_redis()
        cache_key = f"{FOLDER_CACHE_PREFIX}{hashlib.md5(folder_name.encode()).hexdigest()}"
        cached = await redis_conn.get(cache_key)
        if cached:
            return cached.decode()

        folder_id = await self._find_folder(folder_name, parent_id)
        if not folder_id:
            folder_id = await self._create_folder(folder_name, parent_id)
        await redis_conn.setex(cache_key, 86400, folder_id)
        return folder_id

    async def _find_folder(self, folder_name: str, parent_id: str | None) -> str | None:
        query = f"name='{folder_name}' and mimeType='{FOLDER_MIME}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        def _execute():
            return self._service.files().list(
                spaces="drive", fields="files(id, name)", q=query, pageSize=1
            ).execute()

        result = await asyncio.to_thread(_execute)
        files = result.get("files", [])
        return files[0]["id"] if files else None

    async def _create_folder(self, folder_name: str, parent_id: str | None) -> str:
        metadata: dict[str, Any] = {"name": folder_name, "mimeType": FOLDER_MIME}
        if parent_id:
            metadata["parents"] = [parent_id]

        def _execute():
            return self._service.files().create(body=metadata, fields="id").execute()

        result = await asyncio.to_thread(_execute)
        return result["id"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=30),
        retry=retry_if_exception_type((HttpError, ConnectionError)),
    )
    async def upload_file(
        self, local_path: str, drive_folder_id: str, filename: str | None = None, make_public: bool = False
    ) -> dict[str, Any]:
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(f"File not found: {local_path}")
        fname = filename or local.name

        existing = await self._find_file_in_folder(drive_folder_id, fname)
        if existing:
            logger.info("file_already_exists_in_drive", filename=fname, drive_file_id=existing)
            drive_file_id = existing
        else:
            media = MediaFileUpload(str(local), resumable=local.stat().st_size > 5_000_000)
            metadata = {"name": fname, "parents": [drive_folder_id]}

            def _upload():
                return self._service.files().create(body=metadata, media_body=media, fields="id,size").execute()

            result = await asyncio.to_thread(_upload)
            drive_file_id = result["id"]

        if make_public:
            await self._make_public(drive_file_id)

        def _get_meta():
            return self._service.files().get(
                fileId=drive_file_id, fields="id,webViewLink,size"
            ).execute()

        meta = await asyncio.to_thread(_get_meta)
        return {
            "drive_file_id": drive_file_id,
            "drive_file_url": f"https://drive.google.com/file/d/{drive_file_id}/view",
            "filename": fname,
            "size_bytes": int(meta.get("size", local.stat().st_size)),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _find_file_in_folder(self, folder_id: str, filename: str) -> str | None:
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"

        def _execute():
            return self._service.files().list(
                spaces="drive", fields="files(id, name)", q=query, pageSize=1
            ).execute()

        result = await asyncio.to_thread(_execute)
        files = result.get("files", [])
        return files[0]["id"] if files else None

    async def _make_public(self, file_id: str) -> None:
        def _execute():
            return self._service.permissions().create(
                fileId=file_id, body={"role": "reader", "type": "anyone"}
            ).execute()
        await asyncio.to_thread(_execute)

    async def upload_product_outputs(
        self, product_name: str, file_paths: list[str], root_folder_name: str = "ImageFactory Outputs"
    ) -> dict:
        root_id = await self.get_or_create_folder(root_folder_name)
        product_id = await self.get_or_create_folder(product_name, parent_id=root_id)
        results = []
        for fp in file_paths:
            result = await self.upload_file(
                fp, product_id, make_public=settings.google_drive_make_public
            )
            results.append(result)
        folder_url = await self.get_folder_url(product_id)
        return {"folder_url": folder_url, "files": results, "folder_id": product_id}

    async def list_folder_contents(self, folder_id: str) -> list[dict]:
        def _execute():
            return self._service.files().list(
                spaces="drive",
                fields="files(id, name, mimeType, size, webViewLink, createdTime)",
                q=f"'{folder_id}' in parents and trashed=false",
                orderBy="name",
            ).execute()
        result = await asyncio.to_thread(_execute)
        return result.get("files", [])

    async def get_folder_url(self, folder_id: str) -> str:
        def _execute():
            return self._service.files().get(fileId=folder_id, fields="webViewLink").execute()
        result = await asyncio.to_thread(_execute)
        return result.get("webViewLink", f"https://drive.google.com/drive/folders/{folder_id}")

    async def search_folders(self, query: str) -> list[dict]:
        q = f"name contains '{query}' and mimeType='{FOLDER_MIME}' and trashed=false"

        def _execute():
            return self._service.files().list(
                spaces="drive", fields="files(id, name, webViewLink, createdTime)", q=q, orderBy="name"
            ).execute()

        result = await asyncio.to_thread(_execute)
        return result.get("files", [])

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


_drive_manager: GoogleDriveManager | None = None


def get_drive_manager() -> GoogleDriveManager:
    global _drive_manager
    if _drive_manager is None:
        _drive_manager = GoogleDriveManager()
    return _drive_manager
