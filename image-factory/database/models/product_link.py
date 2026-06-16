from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from database.session import Base


class ProductLink(Base):
    __tablename__ = "product_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String(2048), nullable=False, index=True)
    url_hash = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(String(36), default="", index=True)
    batch_id = Column(String(36), default="", index=True)
    status = Column(String(32), default="pending", index=True)
    product_name = Column(String(512), default="")
    category = Column(String(256), default="")
    notes = Column(String(1024), default="")
    priority = Column(Integer, default=0)
    scraped_image_count = Column(Integer, default=0)
    generated_image_count = Column(Integer, default=0)
    error_message = Column(Text, default="")
    failure_type = Column(String(64), default="")
    meta = Column(JSON, default=dict)
    job_id = Column(String(36), default="")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)
    last_generated_at = Column(DateTime, nullable=True)
