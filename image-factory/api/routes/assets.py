from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from database.session import get_session
from database.models.asset import Asset
from sqlalchemy import select
from configs.settings import settings

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("")
async def list_assets():
    return {"items": [], "total": 0}


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
