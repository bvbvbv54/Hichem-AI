from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON, Boolean
from sqlalchemy.orm import relationship

from database.session import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String(32), nullable=False, default="single")
    status = Column(String(32), nullable=False, default="pending", index=True)
    prompt = Column(Text, default="")
    enhanced_prompt = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    template_name = Column(String(128), default="")
    template_category = Column(String(64), default="")
    image_provider = Column(String(32), default="replicate")
    model_name = Column(String(128), default="")
    width = Column(Integer, default=1024)
    height = Column(Integer, default=1024)
    num_images = Column(Integer, default=1)
    parameters = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    project_name = Column(String(255), default="")
    error_message = Column(Text, default="")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    progress = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    parent_job_id = Column(String(36), nullable=True, index=True)
    is_bulk_item = Column(Boolean, default=False)

    assets = relationship("Asset", back_populates="job", cascade="all, delete-orphan")
