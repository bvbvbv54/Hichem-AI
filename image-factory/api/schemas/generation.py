from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):
    prompt: str = Field("", description="Optional initial prompt. If empty, Claude will generate one.")
    subject: str = Field("", description="Subject for Claude to create a prompt from.")
    negative_prompt: str = ""
    template_name: str = ""
    template_parameters: dict[str, Any] = {}
    width: int = 1024
    height: int = 1024
    num_images: int = 1
    model_name: str = ""
    project_name: str = ""
    style: Optional[str] = None
    mood: Optional[str] = None
    context: Optional[str] = None
    use_claude: bool = True
    enhance_prompt: bool = True
    parameters: dict[str, Any] = {}


class BulkGenerationRequest(BaseModel):
    entries: list[GenerationRequest] = Field(..., min_length=1)
    project_name: str = ""
    parallel: bool = True


class ImageGenerationResponse(BaseModel):
    job_id: str
    status: str
    message: str = "Job created successfully"


class BulkGenerationResponse(BaseModel):
    batch_id: str
    total_jobs: int
    status: str = "queued"
    message: str = "Bulk jobs created"
