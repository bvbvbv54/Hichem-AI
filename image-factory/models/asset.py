from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AssetModel(BaseModel):
    id: str
    job_id: str
    filename: str
    original_filename: str = ""
    file_path: str
    file_size: int = 0
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    alt_text: str = ""
    metadata: dict = {}
    delivery_status: str = "pending"
    created_at: datetime = datetime.utcnow()

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}
