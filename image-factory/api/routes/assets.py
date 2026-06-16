from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("")
async def list_assets():
    return {"items": [], "total": 0}
