from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.dependencies import get_job_repo, get_redis
from database.repository import JobRepository
from database.session import get_session
from database.models.job import Job
from database.models.product_link import ProductLink
from models.enums import JobStatus
from configs.settings import settings
from configs.logging import get_logger
from services.nano_banana.credit_balancer import get_credit_balancer
import redis.asyncio as aioredis

logger = get_logger(__name__)

router = APIRouter()


class SubmitGenerationRequest(BaseModel):
    batch_id: str
    project_id: str = ""
    num_images_per_product: int
    image_descriptions: list[str]
    prompt_template: str = ""
    skip_credit_check: bool = False


class CreditCheckRequest(BaseModel):
    batch_id: str
    project_id: str = ""
    num_images_per_product: int = 1
    use_claude: bool = True


class CreditCheckResponse(BaseModel):
    sufficient: bool
    estimated_cost_cents: float
    available_credits_cents: float
    deficit_cents: float
    total_products: int
    total_images_requested: int
    max_images_affordable: int
    warning_message: str
    cost_per_image_cents: float = 1.0
    cost_per_claude_call_cents: float = 0.03
    require_confirmation: bool


@router.post("/products/upload", summary="Upload Excel/CSV product spreadsheet")
async def upload_products(
    file: UploadFile = File(...),
    project_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
    repo: JobRepository = Depends(get_job_repo),
    redis: aioredis.Redis = Depends(get_redis),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="Unsupported file format. Only .xlsx, .xls, and .csv files are accepted.")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    from services.extractor.excel_reader import ExcelReader

    reader = ExcelReader()
    try:
        parse_result = await reader.read_bytes(data, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    if parse_result.valid_rows == 0:
        raise HTTPException(status_code=400, detail="No valid product URLs found in the file.")

    batch_id = str(uuid.uuid4())
    now = datetime.utcnow()

    batch_job = await repo.create({
        "id": batch_id,
        "type": "bulk",
        "status": JobStatus.QUEUED.value,
        "project_name": project_id or "default",
        "num_images": 0,
        "progress": 0.0,
        "meta": {
            "total": parse_result.valid_rows,
            "queued": parse_result.valid_rows,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "filename": file.filename,
        },
    })

    product_list = []
    for product in parse_result.products:
        child_data = {
            "type": "single",
            "status": JobStatus.QUEUED.value,
            "project_name": project_id or "default",
            "parent_job_id": batch_id,
            "is_bulk_item": True,
            "progress": 0.0,
            "prompt": product.product_name or "",
            "meta": {
                "batch_index": product.row_number,
                "product_name": product.product_name or "",
                "url": product.product_url,
                "priority": product.priority,
                "category": product.category or "",
                "notes": product.notes or "",
            },
        }
        child = await repo.create(child_data)
        product_list.append({
            "job_id": child.id,
            "url": product.product_url,
            "product_name": product.product_name or "",
            "priority": product.priority,
            "category": product.category or "",
            "notes": product.notes or "",
            "row_number": product.row_number,
        })

    await _create_product_links(session, product_list, batch_id, project_id or "default")

    from services.time_estimator import TimeEstimator

    estimator = TimeEstimator(redis)
    avg_min = await estimator.estimated_stage_duration("total_product")
    if avg_min <= 0:
        avg_min = settings.batch_avg_minutes_per_product
    estimated_duration_minutes = round(parse_result.valid_rows * avg_min)

    # Dispatch single product tasks for scraping (images + product names)
    from workers.celery_app import celery_app

    dispatched = 0
    for product in product_list:
        if product.get("url"):
            celery_app.send_task("tasks.product.process_single_product", args=[product["job_id"], product["url"], project_id or "default"])
            dispatched += 1

    logger.info("batch_created", batch_id=batch_id, products=parse_result.valid_rows, warnings=len(parse_result.warnings), task_dispatched=dispatched)

    return {
        "batch_id": batch_id,
        "job_id": batch_id,
        "status": "parsed",
        "message": f"Parsed {parse_result.valid_rows} products from file",
        "total_products": parse_result.valid_rows,
        "total_images_scraped": 0,
        "scraped_images": [
            {
                "url": p.product_url,
                "product_name": p.product_name,
                "count": 0,
            }
            for p in parse_result.products
        ],
        "parse_result": {
            "total_rows": parse_result.total_rows,
            "valid_rows": parse_result.valid_rows,
            "skipped_rows": parse_result.skipped_rows,
            "duplicate_rows": parse_result.duplicate_rows,
            "warnings": parse_result.warnings,
        },
        "estimated_duration_minutes": estimated_duration_minutes,
    }


@router.post("/products/check-credits", response_model=CreditCheckResponse, summary="Check Nano Banana credits before generation")
async def check_credits_before_generation(
    req: CreditCheckRequest,
    session: AsyncSession = Depends(get_session),
):
    batch_dir = Path(settings.storage_path) / "uploads" / req.batch_id
    if not batch_dir.exists():
        raise HTTPException(status_code=404, detail="Batch not found. Please upload again.")

    products_file = batch_dir / "products.json"
    if not products_file.exists():
        raise HTTPException(status_code=400, detail="Products data not found.")

    products = json.loads(products_file.read_text())
    product_count = len(products)

    balancer = get_credit_balancer()
    credit_status = await balancer.check_sufficient_credits(
        product_count=product_count,
        images_per_product=req.num_images_per_product,
        use_claude=req.use_claude,
    )

    require_confirmation = not credit_status.sufficient or credit_status.available_credits_cents < 100.0

    return CreditCheckResponse(
        sufficient=credit_status.sufficient,
        estimated_cost_cents=credit_status.estimated_cost_cents,
        available_credits_cents=credit_status.available_credits_cents,
        deficit_cents=credit_status.deficit_cents,
        total_products=product_count,
        total_images_requested=credit_status.total_images_requested,
        max_images_affordable=credit_status.max_images_affordable,
        warning_message=credit_status.warning_message,
        cost_per_image_cents=balancer.COST_PER_IMAGE_CENTS,
        cost_per_claude_call_cents=balancer.COST_PER_CLAUDE_CALL_CENTS,
        require_confirmation=require_confirmation,
    )


@router.get("/products/batch/{batch_id}", summary="Get batch status")
async def get_batch_status(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    children_result = await session.execute(
        select(Job).where(Job.parent_job_id == batch_id).order_by(Job.created_at)
    )
    children = list(children_result.scalars().all())

    queued = sum(1 for j in children if j.status == JobStatus.QUEUED.value)
    processing = sum(1 for j in children if j.status == JobStatus.PROCESSING.value)
    completed = sum(1 for j in children if j.status == JobStatus.COMPLETED.value)
    failed = sum(1 for j in children if j.status == JobStatus.FAILED.value)
    total = len(children)

    meta = batch.meta or {}
    items = []
    for j in children:
        j_meta = j.meta or {}
        items.append({
            "job_id": j.id,
            "url": j_meta.get("url", ""),
            "product_name": j_meta.get("product_name", ""),
            "status": j.status,
            "error_message": j.error_message or "",
            "drive_folder_url": (j.meta or {}).get("drive_folder_url", "") if j.meta else "",
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    estimated_completion = None
    if batch.completed_at:
        estimated_completion = batch.completed_at.isoformat()
    elif total > 0 and completed + failed > 0:
        import math
        done = completed + failed
        elapsed = (datetime.utcnow() - batch.created_at).total_seconds() if batch.created_at else 0
        if done > 0 and elapsed > 0:
            estimated_total = elapsed / (done / total)
            remaining = estimated_total - elapsed
            estimated_completion = datetime.utcnow().timestamp() + max(remaining, 0)

    return {
        "batch_id": batch_id,
        "status": batch.status,
        "paused": meta.get("paused", False),
        "progress": {
            "total": total,
            "queued": queued,
            "processing": processing,
            "completed": completed,
            "failed": failed,
        },
        "estimated_completion_at": estimated_completion,
        "items": items,
    }


@router.post("/products/batch/{batch_id}/pause", summary="Pause batch")
async def pause_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await session.execute(select(Job).where(Job.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    await redis.set(f"batch:{batch_id}:paused", "1", ex=86400)
    meta = dict(batch.meta or {})
    meta["paused"] = True
    await session.execute(update(Job).where(Job.id == batch_id).values(meta=meta, updated_at=datetime.utcnow()))
    await session.commit()
    return {"status": "paused", "batch_id": batch_id}


@router.post("/products/batch/{batch_id}/resume", summary="Resume batch")
async def resume_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await session.execute(select(Job).where(Job.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    await redis.delete(f"batch:{batch_id}:paused")
    meta = dict(batch.meta or {})
    meta["paused"] = False
    await session.execute(update(Job).where(Job.id == batch_id).values(meta=meta, updated_at=datetime.utcnow()))
    await session.commit()
    return {"status": "resumed", "batch_id": batch_id}


@router.post("/products/batch/{batch_id}/retry-failed", summary="Retry failed items in batch")
async def retry_failed_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    children_result = await session.execute(
        select(Job).where(and_(Job.parent_job_id == batch_id, Job.status == JobStatus.FAILED.value))
    )
    failed_jobs = list(children_result.scalars().all())

    retried = 0
    from workers.celery_app import celery_app

    for job in failed_jobs:
        j_meta = job.meta or {}
        url = j_meta.get("url", "")
        await session.execute(
            update(Job).where(Job.id == job.id).values(
                status=JobStatus.QUEUED.value,
                error_message="",
                retry_count=0,
                progress=0.0,
                updated_at=datetime.utcnow(),
            )
        )
        celery_app.send_task("tasks.product.process_single_product", args=[job.id, url, job.project_name])
        retried += 1

    await session.commit()
    logger.info("batch_retry_failed", batch_id=batch_id, count=retried)
    return {"status": "retrying", "batch_id": batch_id, "retried_count": retried}


@router.get("/products/batch/{batch_id}/export", summary="Export batch results as CSV")
async def export_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    children_result = await session.execute(
        select(Job).where(Job.parent_job_id == batch_id).order_by(Job.created_at)
    )
    children = list(children_result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["URL", "Product Name", "Status", "Drive Folder URL", "Error", "Processing Time (s)"])

    for j in children:
        j_meta = j.meta or {}
        duration = ""
        if j.completed_at and j.created_at:
            duration = str(int((j.completed_at - j.created_at).total_seconds()))
        writer.writerow([
            j_meta.get("url", ""),
            j_meta.get("product_name", ""),
            j.status,
            (j.meta or {}).get("drive_folder_url", "") if j.meta else "",
            j.error_message or "",
            duration,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}.csv"},
    )


async def _create_product_links(session, products: list[dict], batch_id: str, project_id: str):
    for product in products:
        url = product.get("url", "")
        if not url:
            continue
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        existing = await session.execute(
            select(ProductLink).where(ProductLink.url_hash == url_hash)
        )
        if existing.scalar_one_or_none():
            continue
        link = ProductLink(
            url=url,
            url_hash=url_hash,
            project_id=project_id or "default",
            batch_id=batch_id,
            status="pending",
            product_name=product.get("product_name", ""),
            category=product.get("category", ""),
            priority=product.get("priority", 0),
        )
        session.add(link)
    await session.commit()


@router.post("/products/generate", summary="Start AI generation with user inputs")
async def start_generation(
    req: SubmitGenerationRequest,
    repo: JobRepository = Depends(get_job_repo),
    session: AsyncSession = Depends(get_session),
):
    if req.num_images_per_product < 1 and req.num_images_per_product != -1:
        raise HTTPException(status_code=400, detail="Number of images must be between 1 and 10, or -1 for auto.")
    if req.num_images_per_product > 10:
        raise HTTPException(status_code=400, detail="Number of images must be between 1 and 10.")

    batch_dir = Path(settings.storage_path) / "uploads" / req.batch_id
    if not batch_dir.exists():
        raise HTTPException(status_code=404, detail="Batch not found. Please upload again.")

    products_file = batch_dir / "products.json"
    if not products_file.exists():
        raise HTTPException(status_code=400, detail="Products data not found.")

    if not req.skip_credit_check:
        balancer = get_credit_balancer()
        products = json.loads(products_file.read_text())
        credit_status = await balancer.check_sufficient_credits(
            product_count=len(products),
            images_per_product=req.num_images_per_product if req.num_images_per_product > 0 else 1,
            use_claude=True,
        )
        if not credit_status.sufficient:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": credit_status.warning_message,
                    "estimated_cost_cents": credit_status.estimated_cost_cents,
                    "available_credits_cents": credit_status.available_credits_cents,
                    "total_products": len(products),
                    "total_images": credit_status.total_images_requested,
                    "max_affordable": credit_status.max_images_affordable,
                    "hint": "Set skip_credit_check=true to bypass or reduce num_images_per_product",
                },
            )

    products = json.loads(products_file.read_text())

    if req.num_images_per_product == -1:
        scraped_images_file = batch_dir / "scraped_images.json"
        per_product_counts = {}
        if scraped_images_file.exists():
            scraped_data = json.loads(scraped_images_file.read_text())
            for item in scraped_data:
                per_product_counts[item["url"]] = item.get("count", 1)
        else:
            product_dirs = [d for d in batch_dir.iterdir() if d.is_dir()]
            for pd in product_dirs:
                image_count = len(list(pd.glob("*")))
                per_product_counts[pd.name] = max(image_count, 1)
    else:
        per_product_counts = {}

    for product in products:
        url = product.get("url", "")
        if url:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            await session.execute(
                update(ProductLink)
                .where(ProductLink.url_hash == url_hash)
                .values(status="generating", updated_at=datetime.utcnow())
            )
    await session.commit()

    batch_job = await repo.create({
        "type": "bulk",
        "status": "pending",
        "project_name": req.project_id or "default",
        "meta": {
            "batch_id": req.batch_id,
            "num_images": req.num_images_per_product,
            "descriptions": req.image_descriptions,
            "prompt_template": req.prompt_template,
            "per_product_counts": per_product_counts,
        },
    })

    from workers.celery_app import celery_app
    celery_app.send_task("tasks.generation.process_bulk_generation", args=[
        batch_job.id,
        req.batch_id,
        req.num_images_per_product,
        req.image_descriptions,
        req.prompt_template,
    ])

    logger.info("generation_started", batch_id=req.batch_id, job_id=batch_job.id, num_images=req.num_images_per_product)

    mode = "auto (match scraped counts)" if req.num_images_per_product == -1 else f"{req.num_images_per_product} per product"
    return {
        "job_id": batch_job.id,
        "batch_id": req.batch_id,
        "status": "queued",
        "message": f"Generating images ({mode}) for {len(products)} products.",
    }
