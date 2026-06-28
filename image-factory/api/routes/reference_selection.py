from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs.logging import get_logger
from services.reference_scoring import score_product_images, save_reference_selection
from database.session import get_session
from database.models.product_link import ProductLink

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["Reference Selection"])


@router.post("/{product_id}/score-references")
async def score_references(
    product_id: str,
    body: dict[str, Any],
):
    reference_count = body.get("reference_count", 3)
    try:
        reference_count = max(3, min(5, int(reference_count)))
    except (ValueError, TypeError):
        reference_count = 3

    user_id = body.get("user_id", "")
    project_id = body.get("project_id", "")

    result = await score_product_images(product_id, reference_count, user_id=user_id, project_id=project_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/{product_id}/save-reference-selection")
async def save_selection(
    product_id: str,
    body: dict[str, Any],
):
    selected_ids = body.get("selected_asset_ids", [])
    auto_select_ids = body.get("auto_select_suggested_ids", [])
    if not isinstance(selected_ids, list):
        raise HTTPException(status_code=400, detail="selected_asset_ids must be a list")

    user_id = body.get("user_id", "")
    project_id = body.get("project_id", "")
    approved = body.get("approved", False)

    result = await save_reference_selection(
        product_id, selected_ids, auto_select_ids,
        user_id=user_id, project_id=project_id, approved=approved,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{product_id}/reference-status")
async def reference_status(
    product_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ProductLink).where(ProductLink.id == product_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Product not found")

    meta = link.meta or {}
    selected_ids = meta.get("reference_selected_ids", [])
    approved = meta.get("reference_approved", False)
    locked = meta.get("reference_locked", False)
    ref_count = len(selected_ids)
    can_generate = approved and ref_count >= 3

    return {
        "product_id": product_id,
        "selected_count": ref_count,
        "approved": approved,
        "locked": locked,
        "can_generate": can_generate,
    }
