from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    prompt: str = ""
    enhanced_prompt: str = ""
    project_name: str = ""
    progress: float = 0.0
    error_message: str = ""
    retry_count: int = 0
    num_images: int = 1
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    assets: list[dict[str, Any]] = []
    batch_items: list[str] = []


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress: float
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: str = ""


class BatchJobResponse(BaseModel):
    batch_id: str
    parent_job_id: str
    total: int
    completed: int
    failed: int
    status: str
    progress: float
    items: list[JobResponse] = []
