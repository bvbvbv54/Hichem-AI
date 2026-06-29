from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProductLinkSchema(BaseModel):
    id: str
    url: str
    url_hash: str
    project_id: str = ""
    batch_id: str = ""
    status: str = "pending"
    product_name: str = ""
    category: str = ""
    priority: int = 0
    scraped_image_count: int = 0
    generated_image_count: int = 0
    error_message: str = ""
    failure_type: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    job_id: str = ""
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_scraped_at: Optional[datetime] = None
    last_generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class ContentListResponse(BaseModel):
    products: list[ProductLinkSchema]
    total: int
    limit: int
    offset: int


class ProductDetailResponse(BaseModel):
    product: ProductLinkSchema
    scraped_images: list[dict[str, Any]] = Field(default_factory=list)
    generated_images: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    reference_status: dict[str, Any] = Field(default_factory=dict)
