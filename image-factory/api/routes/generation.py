from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.generation import (
    GenerationRequest,
    BulkGenerationRequest,
    ImageGenerationResponse,
    BulkGenerationResponse,
)
from api.dependencies import get_job_repo
from database.session import get_session
from database.repository import JobRepository
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/generate", response_model=ImageGenerationResponse, summary="Generate a single image")
async def generate_image(
    request: GenerationRequest,
    repo: JobRepository = Depends(get_job_repo),
):
    if not request.prompt and not request.subject:
        raise HTTPException(
            status_code=422,
            detail="Either 'prompt' or 'subject' must be provided",
        )

    job_data = {
        "type": "single",
        "status": "pending",
        "prompt": request.prompt,
        "enhanced_prompt": "",
        "negative_prompt": request.negative_prompt,
        "template_name": request.template_name,
        "width": request.width,
        "height": request.height,
        "num_images": request.num_images,
        "model_name": request.model_name,
        "project_name": request.project_name,
        "parameters": {
            "style": request.style,
            "mood": request.mood,
            "context": request.context,
            "subject": request.subject,
            "use_claude": request.use_claude,
            "enhance_prompt": request.enhance_prompt,
            **request.parameters,
        },
    }

    job = await repo.create(job_data)

    from tasks.generation import process_generation
    process_generation.delay(job.id)

    logger.info("generation_job_created", job_id=job.id)
    return ImageGenerationResponse(job_id=job.id, status="queued")


@router.post("/generate/bulk", response_model=BulkGenerationResponse, summary="Generate multiple images")
async def bulk_generate(
    request: BulkGenerationRequest,
    repo: JobRepository = Depends(get_job_repo),
):
    batch_id = str(uuid.uuid4())
    parent_data = {
        "type": "bulk",
        "status": "pending",
        "project_name": request.project_name,
        "metadata": {"batch_id": batch_id, "total": len(request.entries)},
    }
    parent_job = await repo.create(parent_data)

    child_ids = []
    for entry in request.entries:
        child_data = {
            "type": "single",
            "status": "pending",
            "prompt": entry.prompt,
            "negative_prompt": entry.negative_prompt,
            "template_name": entry.template_name,
            "width": entry.width,
            "height": entry.height,
            "num_images": entry.num_images,
            "model_name": entry.model_name,
            "project_name": entry.project_name or request.project_name,
            "parent_job_id": parent_job.id,
            "is_bulk_item": True,
            "parameters": {
                "style": entry.style,
                "mood": entry.mood,
                "context": entry.context,
                "subject": entry.subject,
                "use_claude": entry.use_claude,
                "enhance_prompt": entry.enhance_prompt,
                **entry.parameters,
            },
        }
        child = await repo.create(child_data)
        child_ids.append(child.id)

    from tasks.generation import process_bulk_generation
    process_bulk_generation.delay(parent_job.id, child_ids)

    logger.info("bulk_jobs_created", batch_id=batch_id, count=len(child_ids))
    return BulkGenerationResponse(
        batch_id=batch_id,
        total_jobs=len(child_ids),
    )
