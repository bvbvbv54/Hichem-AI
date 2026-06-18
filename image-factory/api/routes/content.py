from __future__ import annotations

import hashlib
from datetime import datetime, timezone
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
from services.translation_service import batch_translate, contains_chinese

logger = get_logger(__name__)

from PIL import Image as PILImage

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

    product_names = [link.product_name or "" for link in links]
    translated = await batch_translate(product_names) if any(contains_chinese(n) for n in product_names) else {}
    for link in links:
        name = link.product_name or ""
        if name in translated:
            link.product_name = translated[name]

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
        select(func.count(ProductLink.id)).where(ProductLink.status.in_(["failed", "error"]))
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

    # Get all jobs for this product URL
    jobs_result = await session.execute(
        select(Job).where(
            Job.meta["url"].as_string() == link.url
        ).order_by(desc(Job.created_at))
    )
    all_jobs = list(jobs_result.scalars().all())

    # Also get by direct job_id link
    direct_jobs = []
    if link.job_id:
        direct = await session.execute(select(Job).where(Job.id == link.job_id))
        dj = direct.scalar_one_or_none()
        if dj:
            direct_jobs = [dj]

    merged_jobs = {j.id: j for j in all_jobs + direct_jobs}
    jobs = list(merged_jobs.values())
    jobs.sort(key=lambda j: j.created_at or datetime.min, reverse=True)

    seen_scraped_paths: set[str] = set()
    seen_generated_paths: set[str] = set()
    seen_scraped_content: set[tuple] = set()

    for job in jobs:
        assets_result = await session.execute(
            select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
        )
        assets = list(assets_result.scalars().all())

        for asset in assets:
            fp = asset.file_path or ""
            content_key = (asset.width, asset.height, asset.file_size)
            if content_key[0] and content_key[1] and content_key[0] >= 200:
                if content_key in seen_scraped_content:
                    continue
                seen_scraped_content.add(content_key)
            img_info = {
                "id": asset.id,
                "job_id": asset.job_id,
                "filename": asset.filename,
                "file_path": fp,
                "file_size": asset.file_size,
                "mime_type": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "alt_text": asset.alt_text,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }
            meta = asset.meta or {}
            is_scraped = meta.get("type") == "scraped" or "scraped" in (asset.filename or "")
            target_set = seen_scraped_paths if is_scraped else seen_generated_paths
            if fp and fp in target_set:
                continue
            if fp:
                target_set.add(fp)
            if is_scraped:
                scraped_images.append(img_info)
            else:
                generated_images.append(img_info)

        # Also get scraped image paths from job meta
        job_meta = job.meta or {}
        saved = job_meta.get("saved_assets", [])
        for img_path in saved:
            if img_path in seen_scraped_paths:
                continue
            seen_scraped_paths.add(img_path)
            img_id = hashlib.sha256(img_path.encode()).hexdigest()[:12]
            scraped_images.append({
                "id": img_id,
                "job_id": job.id,
                "filename": Path(img_path).name,
                "file_path": img_path,
                "file_size": 0,
                "mime_type": "image/jpeg",
                "width": None,
                "height": None,
                "alt_text": "",
                "created_at": job.completed_at.isoformat() if job.completed_at else "",
            })

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


@router.post("/products/{product_id}/dedup")
async def dedup_product_images(
    product_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ProductLink).where(ProductLink.id == product_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Product not found")

    jobs_result = await session.execute(
        select(Job).where(Job.meta["url"].as_string() == link.url).order_by(desc(Job.created_at))
    )
    all_jobs = list(jobs_result.scalars().all())
    if link.job_id:
        direct = await session.execute(select(Job).where(Job.id == link.job_id))
        dj = direct.scalar_one_or_none()
        if dj:
            all_jobs.append(dj)

    seen_content: dict[tuple, int] = {}
    deleted_count = 0
    kept_count = 0
    deleted_paths: list[str] = []
    asset_ids_to_delete: list[str] = []

    for job in all_jobs:
        assets_result = await session.execute(
            select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
        )
        assets = list(assets_result.scalars().all())

        for asset in assets:
            fp = asset.file_path or ""
            fpath = Path(fp)
            if not fpath.exists():
                continue
            fsize = fpath.stat().st_size
            try:
                with PILImage.open(fp) as img:
                    content_key = (img.width, img.height, fsize)
            except Exception:
                content_key = (0, 0, fsize)

            if content_key in seen_content:
                fpath.unlink(missing_ok=True)
                asset_ids_to_delete.append(asset.id)
                deleted_paths.append(fp)
                deleted_count += 1
            else:
                seen_content[content_key] = 1
                kept_count += 1

        # Also check job meta saved_assets
        job_meta = job.meta or {}
        saved = job_meta.get("saved_assets", [])
        for meta_path in saved:
            if meta_path in deleted_paths:
                continue
            mp = Path(meta_path)
            if not mp.exists():
                continue
            fsize = mp.stat().st_size
            try:
                with PILImage.open(str(mp)) as img:
                    content_key = (img.width, img.height, fsize)
            except Exception:
                content_key = (0, 0, fsize)
            if content_key in seen_content:
                mp.unlink(missing_ok=True)
                deleted_paths.append(meta_path)
                deleted_count += 1
            else:
                seen_content[content_key] = 1
                kept_count += 1

    # Delete duplicate assets from DB
    if asset_ids_to_delete:
        from sqlalchemy import delete as sql_delete
        await session.execute(
            sql_delete(Asset).where(Asset.id.in_(asset_ids_to_delete))
        )
        await session.commit()

    return {
        "product_id": product_id,
        "dedup_deleted": deleted_count,
        "kept": kept_count,
        "deleted_asset_ids": asset_ids_to_delete,
    }
