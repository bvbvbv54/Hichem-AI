from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_job_repo, get_asset_repo
from api.schemas.content import ContentListResponse, ProductDetailResponse, ProductLinkSchema
from database.session import get_session
from database.models.job import Job
from database.models.asset import Asset
from database.models.product_link import ProductLink
from database.repository import JobRepository, AssetRepository
from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/content", tags=["Content"])


@router.get("/products", response_model=ContentListResponse)
async def list_content_products(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    query = select(ProductLink)
    count_query = select(func.count(ProductLink.id))

    conditions = []
    if project_id:
        conditions.append(ProductLink.project_id == project_id)
    if status:
        conditions.append(ProductLink.status == status)
    if search:
        conditions.append(ProductLink.product_name.ilike(f"%{search}%"))

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    query = query.order_by(desc(ProductLink.updated_at)).limit(limit).offset(offset)
    result = await session.execute(query)
    links = list(result.scalars().all())

    return ContentListResponse(
        products=[ProductLinkSchema.model_validate(link) for link in links],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/stats")
async def get_content_stats(
    session: AsyncSession = Depends(get_session),
):
    total_result = await session.execute(select(func.count(ProductLink.id)))
    total = total_result.scalar() or 0

    pending = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "pending")
    )
    scraping = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "scraping")
    )
    scraped = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "scraped")
    )
    generating = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "generating")
    )
    completed = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "completed")
    )
    failed = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "failed")
    )
    skipped = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status == "skipped")
    )

    return {
        "total": total,
        "pending": pending.scalar() or 0,
        "scraping": scraping.scalar() or 0,
        "scraped": scraped.scalar() or 0,
        "generating": generating.scalar() or 0,
        "completed": completed.scalar() or 0,
        "failed": failed.scalar() or 0,
        "skipped": skipped.scalar() or 0,
    }


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
async def get_product_detail(
    product_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ProductLink).where(ProductLink.id == product_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Product not found")

    scraped_images = []
    generated_images = []
    jobs_list = []

    if link.job_id:
        jobs_result = await session.execute(
            select(Job).where(
                and_(
                    Job.meta.contains({"url": link.url}).as_comparison(1, 2),
                    Job.status == "completed"
                )
            )
            .order_by(desc(Job.created_at))
        )
        jobs = list(jobs_result.scalars().all())

        for job in jobs:
            assets_result = await session.execute(
                select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
            )
            assets = list(assets_result.scalars().all())

            for asset in assets:
                img_info = {
                    "id": asset.id,
                    "job_id": asset.job_id,
                    "filename": asset.filename,
                    "file_path": asset.file_path,
                    "file_size": asset.file_size,
                    "mime_type": asset.mime_type,
                    "width": asset.width,
                    "height": asset.height,
                    "alt_text": asset.alt_text,
                    "created_at": asset.created_at.isoformat() if asset.created_at else None,
                }
                meta = asset.meta or {}
                if meta.get("type") == "scraped" or "scraped" in asset.filename:
                    scraped_images.append(img_info)
                else:
                    generated_images.append(img_info)

            jobs_list.append({
                "id": job.id,
                "status": job.status,
                "type": job.type,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "progress": job.progress,
                "error_message": job.error_message or "",
            })

    return ProductDetailResponse(
        product=ProductLinkSchema.model_validate(link),
        scraped_images=scraped_images,
        generated_images=generated_images,
        jobs=jobs_list,
    )


@router.post("/products/{product_id}/retry")
async def retry_content_product(
    product_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ProductLink).where(ProductLink.id == product_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Product not found")

    if link.status not in ("failed", "error"):
        raise HTTPException(status_code=400, detail="Only failed products can be retried")

    from datetime import datetime
    link.status = "pending"
    link.error_message = ""
    link.failure_type = ""
    link.retry_count = (link.retry_count or 0) + 1
    link.updated_at = datetime.utcnow()

    await session.commit()

    if link.job_id:
        from workers.celery_app import celery_app
        celery_app.send_task("tasks.product.process_single_product", args=[link.job_id, link.url, link.project_id])

    return {"status": "retrying", "product_id": product_id, "url": link.url}
