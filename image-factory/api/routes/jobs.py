from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.job import JobResponse, JobListResponse, JobStatusResponse, BatchJobResponse
from api.dependencies import get_job_repo, get_asset_repo, get_session
from database.repository import JobRepository, AssetRepository
from database.models.product_link import ProductLink
from models.enums import JobStatus
from services.notifications import send_notification, NotificationLevel

router = APIRouter()


def _job_to_response(job, batch_items: list[str] | None = None) -> JobResponse:
    assets = []
    if hasattr(job, "assets"):
        assets = [
            {
                "id": a.id,
                "filename": a.filename,
                "file_path": a.file_path,
                "file_size": a.file_size,
                "mime_type": a.mime_type,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in (job.assets or [])
        ]
    return JobResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        prompt=job.prompt or "",
        enhanced_prompt=job.enhanced_prompt or "",
        project_name=job.project_name or "",
        progress=job.progress or 0.0,
        error_message=job.error_message or "",
        retry_count=job.retry_count or 0,
        num_images=job.num_images or 1,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        assets=assets,
        batch_items=batch_items or [],
    )


@router.get("/jobs/active", summary="List active scraping jobs with progress")
async def list_active_jobs(
    session: AsyncSession = Depends(get_session),
):
    active_statuses = ["pending", "queued", "scraping"]
    result = await session.execute(
        select(ProductLink.project_id).where(ProductLink.status.in_(active_statuses)).distinct()
    )
    active_project_ids = [row[0] for row in result.all()]

    projects = []
    for pid in active_project_ids:
        all_links = await session.execute(
            select(ProductLink.status).where(ProductLink.project_id == pid)
        )
        statuses = [row[0] for row in all_links.all()]
        total = len(statuses)
        completed = sum(1 for s in statuses if s in ("scraped", "completed"))
        failed = sum(1 for s in statuses if s in ("failed", "error"))
        projects.append({
            "project_id": pid,
            "project_name": pid,
            "total_products": total,
            "completed_count": completed,
            "failed_count": failed,
            "progress_pct": round((completed + failed) / total * 100, 1) if total > 0 else 0,
        })

    return {"active_projects": projects, "total_active": len(projects)}


@router.get("/jobs", response_model=JobListResponse, summary="List all jobs")
async def list_jobs(
    status: Optional[str] = None,
    project: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    repo: JobRepository = Depends(get_job_repo),
):
    status_enum = JobStatus(status) if status else None
    jobs, total = await repo.list(
        status=status_enum,
        project=project,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="Get job details")
async def get_job(
    job_id: str,
    repo: JobRepository = Depends(get_job_repo),
    asset_repo: AssetRepository = Depends(get_asset_repo),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    children = await repo.list_by_parent(job_id)
    batch_items = [c.id for c in children]
    return _job_to_response(job, batch_items=batch_items)


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse, summary="Get job status")
async def get_job_status(
    job_id: str,
    repo: JobRepository = Depends(get_job_repo),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        id=job.id,
        status=job.status,
        progress=job.progress or 0.0,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message or "",
    )


@router.post("/jobs/{job_id}/cancel", summary="Cancel a job")
async def cancel_job(
    job_id: str,
    repo: JobRepository = Depends(get_job_repo),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Job already in terminal state: {job.status}")

    await repo.update_status(job_id, JobStatus.CANCELLED)
    await send_notification(
        user_id="",
        title="Job cancelled",
        message=f"Job {job_id} was cancelled. Product: {job.prompt or job.project_name}",
        event_type="job_cancelled",
        level=NotificationLevel.WARNING,
    )
    return {"status": "cancelled", "job_id": job_id}


@router.post("/jobs/{job_id}/retry", summary="Retry a failed job")
async def retry_job(
    job_id: str,
    repo: JobRepository = Depends(get_job_repo),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Can only retry failed jobs")

    await repo.update(job_id, {
        "status": "pending",
        "error_message": "",
        "retry_count": (job.retry_count or 0) + 1,
    })

    from tasks.generation import process_generation
    process_generation.delay(job_id)

    return {"status": "retrying", "job_id": job_id}


@router.get("/jobs/bulk/{parent_job_id}", response_model=BatchJobResponse, summary="Get bulk job progress")
async def get_bulk_job(
    parent_job_id: str,
    repo: JobRepository = Depends(get_job_repo),
):
    parent = await repo.get(parent_job_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent job not found")

    children = await repo.list_by_parent(parent_job_id)
    completed = sum(1 for c in children if c.status == "completed")
    failed = sum(1 for c in children if c.status == "failed")
    total = len(children)
    progress = (completed / total * 100) if total > 0 else 0

    return BatchJobResponse(
        batch_id=parent.meta.get("batch_id", "") if parent.meta else "",
        parent_job_id=parent_job_id,
        total=total,
        completed=completed,
        failed=failed,
        status=parent.status,
        progress=progress,
        items=[_job_to_response(c) for c in children],
    )


@router.get("/stats", summary="Get system statistics")
async def get_stats(
    repo: JobRepository = Depends(get_job_repo),
):
    return await repo.get_stats()
