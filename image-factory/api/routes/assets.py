from __future__ import annotations

import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, func, text as sqlalchemy_text
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from database.session import get_session
from database.models.asset import Asset
from database.models.product_link import ProductLink
from database.models.job import Job
from database.models.setting import Setting
from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/assets", tags=["Assets"])

BANNED_HASHES_SETTING_KEY = "banned_image_hashes"

class BanImageRequest(BaseModel):
    asset_id: str
    hash: str = ""
    filename: str = ""

async def _get_banned_hashes(session) -> set[str]:
    result = await session.execute(
        select(Setting).where(Setting.key == BANNED_HASHES_SETTING_KEY)
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        return set(json.loads(setting.value))
    return set()

async def _add_banned_hash(session, hash_str: str) -> None:
    hashes = await _get_banned_hashes(session)
    hashes.add(hash_str)
    await session.execute(
        sqlalchemy_text(
            "INSERT INTO settings (key, value, updated_at) VALUES (:key, :value, :now) "
            "ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = :now"
        ),
        {"key": BANNED_HASHES_SETTING_KEY, "value": json.dumps(list(hashes)), "now": datetime.utcnow()},
    )
    await session.commit()
    # Also update Redis
    try:
        import redis.asyncio as aioredis
        r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await r.sadd("global_rejected_hashes", hash_str)
        await r.aclose()
    except Exception:
        pass

async def _remove_banned_hash(session, hash_str: str) -> None:
    hashes = await _get_banned_hashes(session)
    hashes.discard(hash_str)
    await session.execute(
        sqlalchemy_text(
            "INSERT INTO settings (key, value, updated_at) VALUES (:key, :value, :now) "
            "ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = :now"
        ),
        {"key": BANNED_HASHES_SETTING_KEY, "value": json.dumps(list(hashes)), "now": datetime.utcnow()},
    )
    await session.commit()
    try:
        import redis.asyncio as aioredis
        r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await r.srem("global_rejected_hashes", hash_str)
        await r.aclose()
    except Exception:
        pass


@router.get("")
async def list_assets(
    project_id: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    query = select(Asset)
    conditions = []
    if project_id:
        conditions.append(Asset.project_id == project_id)
    if status:
        conditions.append(Asset.status == status)
    if search:
        conditions.append(Asset.filename.ilike(f"%{search}%"))
    if conditions:
        from sqlalchemy import and_
        query = query.where(and_(*conditions))
    count_query = select(Asset.id).select_from(select(Asset).where(and_(*conditions) if conditions else True).subquery())
    count_result = await session.execute(select(func.count()).select_from(count_query))
    total = count_result.scalar() or 0
    result = await session.execute(query.order_by(desc(Asset.created_at)).limit(limit).offset(offset))
    assets = result.scalars().all()
    return {"assets": [{"id": a.id, "job_id": a.job_id, "project_id": a.project_id, "filename": a.filename, "file_path": a.file_path, "file_size": a.file_size, "mime_type": a.mime_type, "width": a.width, "height": a.height, "alt_text": a.alt_text, "status": a.status, "meta": a.meta or {}, "created_at": a.created_at.isoformat() if a.created_at else "", "updated_at": a.updated_at.isoformat() if a.updated_at else ""} for a in assets], "total": total}


async def _serve_file(file_path_str: str) -> FileResponse:
    file_path = Path(file_path_str)
    if not file_path.exists():
        alt_path = Path(settings.storage_path) / file_path_str
        if alt_path.exists():
            file_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="File not found on disk")
    ext = file_path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
    return FileResponse(path=str(file_path), media_type=mime_map.get(ext, "image/png"))


@router.get("/{asset_id}/file")
async def get_asset_file(
    asset_id: str,
    session: AsyncSession = Depends(get_session),
):
    # Try Asset table first
    result = await session.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if asset:
        return await _serve_file(asset.file_path)

    # Try scraped image from product detail (hashed path)
    # asset_id is a hash - search all job metas for matching path
    jobs_result = await session.execute(
        select(Job).order_by(desc(Job.created_at)).limit(2000)
    )
    for job in jobs_result.scalars().all():
        job_meta = job.meta or {}
        saved = job_meta.get("saved_assets", [])
        for img_path in saved:
            img_id = hashlib.sha256(img_path.encode()).hexdigest()[:12]
            if img_id == asset_id:
                return await _serve_file(img_path)

    raise HTTPException(status_code=404, detail="Asset not found")


@router.get("/{asset_id}/download")
async def download_asset(
    asset_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = Path(asset.file_path)
    if not file_path.exists():
        alt_path = Path(settings.storage_path) / asset.file_path
        if alt_path.exists():
            file_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="Asset file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=asset.mime_type or "image/png",
        filename=asset.filename,
    )


@router.get("/banned-hashes")
async def list_banned_hashes(
    session: AsyncSession = Depends(get_session),
):
    hashes = await _get_banned_hashes(session)
    return {"hashes": list(hashes)}


@router.post("/ban")
async def ban_image_hash(
    req: BanImageRequest,
    session: AsyncSession = Depends(get_session),
):
    if not req.hash:
        raise HTTPException(status_code=400, detail="hash is required")
    await _add_banned_hash(session, req.hash)
    logger.info("image_hash_banned", hash=req.hash, asset_id=req.asset_id, filename=req.filename)
    return {"status": "banned", "hash": req.hash}


@router.post("/unban")
async def unban_image_hash(
    req: BanImageRequest,
    session: AsyncSession = Depends(get_session),
):
    if not req.hash:
        raise HTTPException(status_code=400, detail="hash is required")
    await _remove_banned_hash(session, req.hash)
    logger.info("image_hash_unbanned", hash=req.hash, asset_id=req.asset_id)
    return {"status": "unbanned", "hash": req.hash}
