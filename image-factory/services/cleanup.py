from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from configs.settings import settings
from configs.logging import get_logger
from database.models.asset import Asset
from database.models.feature_cache import FeatureCache
from services.settings_service import get_setting
from services.storage.local import LocalStorage

logger = get_logger(__name__)

AUTO_CLEANUP_DEFAULT = "true"


async def is_safe_to_delete_local(asset_id: str, session: AsyncSession) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    result = await session.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        return False, ["asset not found"]

    meta = asset.meta or {}
    r2_url = meta.get("r2_url", "")
    if not r2_url:
        return False, ["r2_url is null or empty"]

    is_scraped = meta.get("type") == "scraped"
    if is_scraped:
        fc_result = await session.execute(
            select(FeatureCache).where(FeatureCache.asset_id == asset_id)
        )
        fc = fc_result.scalar_one_or_none()
        if not fc:
            return False, ["scraped asset has no FeatureCache row — scoring incomplete"]

    local_path = Path(asset.file_path) if asset.file_path else None
    if not local_path or not local_path.exists():
        return True, ["local file already gone — nothing to delete"]

    return True, []


async def verify_r2_url(r2_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(r2_url, follow_redirects=True)
            if resp.status_code == 200:
                return True
            logger.warning("r2_head_failed", r2_url=r2_url[:80], status=resp.status_code)
            return False
    except Exception as e:
        logger.warning("r2_head_exception", r2_url=r2_url[:80], error=str(e))
        return False


async def run_cleanup(session: AsyncSession, dry_run: bool = False) -> dict:
    enabled = await get_setting("auto_cleanup_local", session, AUTO_CLEANUP_DEFAULT)
    if enabled.lower() not in ("true", "1", "yes"):
        logger.info("cleanup_skipped_disabled")
        return {"status": "skipped", "reason": "auto_cleanup_local disabled", "deleted": 0, "skipped": 0, "errors": 0}

    result = await session.execute(
        select(Asset).where(
            sa_text("meta->>'r2_url' IS NOT NULL AND meta->>'r2_url' != ''")
        )
    )
    assets = list(result.scalars().all())

    deleted = 0
    skipped = 0
    errors = 0

    for asset in assets:
        safe, reasons = await is_safe_to_delete_local(asset.id, session)
        if not safe:
            skipped += 1
            continue

        meta = asset.meta or {}
        r2_url = meta.get("r2_url", "")
        local_path = Path(asset.file_path) if asset.file_path else None

        if not local_path or not local_path.exists():
            skipped += 1
            continue

        r2_ok = await verify_r2_url(r2_url)
        if not r2_ok:
            logger.warning("cleanup_head_failed", asset_id=asset.id, r2_url=r2_url[:80], local_path=str(local_path))
            errors += 1
            continue

        if dry_run:
            logger.info("cleanup_dry_run", asset_id=asset.id, local_path=str(local_path), r2_url=r2_url[:80])
            deleted += 1
            continue

        try:
            Path(local_path).unlink(missing_ok=True)
            logger.info("cleanup_deleted", asset_id=asset.id, local_path=str(local_path), r2_url=r2_url[:80])
            deleted += 1
        except Exception as e:
            logger.error("cleanup_delete_failed", asset_id=asset.id, local_path=str(local_path), error=str(e))
            errors += 1

    logger.info("cleanup_complete", deleted=deleted, skipped=skipped, errors=errors)
    return {"status": "completed", "dry_run": dry_run, "deleted": deleted, "skipped": skipped, "errors": errors}


async def get_local_storage_size() -> int:
    total = 0
    base = settings.storage_path
    if not base.exists():
        return 0
    try:
        for f in base.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception as e:
        logger.warning("storage_size_error", error=str(e))
    return total
