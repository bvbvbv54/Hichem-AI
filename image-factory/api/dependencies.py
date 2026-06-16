from __future__ import annotations

from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from configs.settings import settings
from database.session import get_session
from database.repository import JobRepository, AssetRepository

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it via X-API-Key header.",
        )
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return api_key


async def get_job_repo(session: AsyncSession = Depends(get_session)) -> JobRepository:
    return JobRepository(session)


async def get_asset_repo(session: AsyncSession = Depends(get_session)) -> AssetRepository:
    return AssetRepository(session)


async def get_redis() -> aioredis.Redis:
    r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
    try:
        yield r
    finally:
        await r.aclose()
