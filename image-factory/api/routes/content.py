from __future__ import annotations

import hashlib
import uuid
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

    for link in links:
        if not link.display_title:
            link.display_title = link.product_name or ""

    return ContentListResponse(
        products=[ProductLinkSchema.model_validate(link) for link in links],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/stats")
async def get_content_stats(
    session: AsyncSession = Depends(get_session),
    status: str = "",
    search: str = "",
):
    base_filter = True
    if status:
        base_filter = ProductLink.status == status
    if search:
        base_filter = base_filter & ProductLink.product_name.ilike(f"%{search}%") if isinstance(base_filter, bool) else base_filter & ProductLink.product_name.ilike(f"%{search}%")

    async def count_with_filter(status_filter=None):
        q = select(func.count(ProductLink.id))
        conditions = []
        if isinstance(status_filter, list):
            conditions.append(ProductLink.status.in_(status_filter))
        elif status_filter:
            conditions.append(ProductLink.status == status_filter)
        if search:
            conditions.append(ProductLink.product_name.ilike(f"%{search}%"))
        r = await session.execute(q.where(and_(*conditions)) if conditions else q)
        return r.scalar() or 0

    total = await count_with_filter()
    pending = await count_with_filter("pending")
    scraping = await count_with_filter("scraping")
    scraped = await count_with_filter("scraped")
    generating = await count_with_filter("generating")
    completed = await count_with_filter("completed")
    failed = await count_with_filter(["failed", "error"])
    skipped = await count_with_filter("skipped")

    return {
        "total": total,
        "pending": pending,
        "scraping": scraping,
        "scraped": scraped,
        "generating": generating,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
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

    for job in jobs:
        assets_result = await session.execute(
            select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
        )
        assets = list(assets_result.scalars().all())

        for asset in assets:
            fp = asset.file_path or ""
            if fp and fp in (seen_scraped_paths | seen_generated_paths):
                continue
            meta = asset.meta or {}
            is_scraped = meta.get("type") == "scraped" or "scraped" in (asset.filename or "")
            asset_meta = asset.meta or {}
            r2_url = asset_meta.get("r2_url", "")
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
                "r2_url": r2_url,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }
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
            if not Path(img_path).exists():
                continue
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

    pl_meta = link.meta or {}
    ref_ids = pl_meta.get("reference_selected_ids", [])
    ref_approved = pl_meta.get("reference_approved", False)
    ref_locked = pl_meta.get("reference_locked", False)

    return ProductDetailResponse(
        product=ProductLinkSchema.model_validate(link),
        scraped_images=scraped_images,
        generated_images=generated_images,
        jobs=jobs_list,
        reference_status={
            "selected_count": len(ref_ids),
            "approved": ref_approved,
            "locked": ref_locked,
            "can_generate": ref_approved and len(ref_ids) >= 3,
        },
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

    # Deduplicate jobs by ID
    seen_job_ids: set[str] = set()
    unique_jobs = []
    for j in all_jobs:
        if j.id not in seen_job_ids:
            seen_job_ids.add(j.id)
            unique_jobs.append(j)
    all_jobs = unique_jobs

    deleted_count = 0
    kept_count = 0
    deleted_paths: list[str] = []
    asset_ids_to_delete: list[str] = []
    all_image_paths: list[str] = []

    for job in all_jobs:
        assets_result = await session.execute(
            select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
        )
        assets = list(assets_result.scalars().all())

        for asset in assets:
            fp = asset.file_path or ""
            fpath = Path(fp)
            if fpath.exists():
                all_image_paths.append(str(fpath))

        # Also check job meta saved_assets
        job_meta = job.meta or {}
        saved = job_meta.get("saved_assets", [])
        for meta_path in saved:
            mp = Path(meta_path)
            if mp.exists():
                all_image_paths.append(str(mp))

    # Run difPy dedup on all collected image paths
    if len(all_image_paths) >= 2:
        import tempfile
        import shutil
        temp_dedup_dir = Path(tempfile.mkdtemp(prefix="dedup_"))
        try:
            path_map: dict[str, str] = {}
            for img_path in all_image_paths:
                src = Path(img_path)
                dst = temp_dedup_dir / src.name
                if dst.exists():
                    dst = temp_dedup_dir / f"{uuid.uuid4().hex[:8]}_{src.name}"
                shutil.copy2(str(src), str(dst))
                path_map[str(dst)] = str(src)

            import difPy
            dif = difPy.build(str(temp_dedup_dir), recursive=False, in_folder=True,
                              limit_extensions=True, px_size=50,
                              show_progress=False, processes=1)
            search = difPy.search(dif, similarity='duplicates', rotate=True,
                                  same_dim=False, show_progress=False, processes=1)

            deleted_local: set[str] = set()
            for dup_path in search.lower_quality:
                orig_path = path_map.get(dup_path)
                if orig_path:
                    Path(orig_path).unlink(missing_ok=True)
                    deleted_paths.append(orig_path)
                    deleted_local.add(orig_path)
                    deleted_count += 1

            # Remove deleted files from saved_assets lists and mark assets for deletion
            for job in all_jobs:
                assets_result = await session.execute(
                    select(Asset).where(Asset.job_id == job.id)
                )
                for asset in assets_result.scalars().all():
                    if asset.file_path in deleted_local:
                        asset_ids_to_delete.append(asset.id)

                job_meta = job.meta or {}
                saved = job_meta.get("saved_assets", [])
                updated_saved = [p for p in saved if p not in deleted_local]
                if len(updated_saved) != len(saved):
                    job_meta["saved_assets"] = updated_saved
                    from sqlalchemy import update as sql_update
                    await session.execute(
                        sql_update(Job).where(Job.id == job.id).values(meta=job_meta)
                    )

        finally:
            shutil.rmtree(temp_dedup_dir, ignore_errors=True)

    kept_count = len(all_image_paths) - deleted_count

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
