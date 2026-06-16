from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
async def analytics_summary():
    return {"status": "not_implemented"}
