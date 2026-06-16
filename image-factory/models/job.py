from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobModel(BaseModel):
    id: str
    type: str  # JobType
    status: str  # JobStatus
    prompt: str = ""
    enhanced_prompt: str = ""
    negative_prompt: str = ""
    template_name: str = ""
    template_category: str = ""
    image_provider: str = "replicate"
    model_name: str = ""
    width: int = 1024
    height: int = 1024
    num_images: int = 1
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    project_name: str = ""
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    progress: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    parent_job_id: Optional[str] = None
    is_bulk_item: bool = False

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}
