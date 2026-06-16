from __future__ import annotations

import time

from fastapi import APIRouter

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", summary="Health check endpoint")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "timestamp": time.time(),
    }


@router.get("/health/ready", summary="Readiness check")
async def readiness_check():
    from database.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ready" if db_ok else "not_ready",
        "database": "connected" if db_ok else "disconnected",
    }
