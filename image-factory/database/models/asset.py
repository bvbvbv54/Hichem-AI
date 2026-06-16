from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from database.session import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), default="")
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0)
    mime_type = Column(String(64), default="image/png")
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    alt_text = Column(Text, default="")
    meta = Column(JSON, default=dict)
    delivery_status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="assets")
