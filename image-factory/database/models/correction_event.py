from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String, Boolean

from database.session import Base


class CorrectionEvent(Base):
    __tablename__ = "correction_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True, default="")
    project_id = Column(String(36), nullable=False, default="")
    product_id = Column(String(36), nullable=False, default="")
    asset_id = Column(String(36), nullable=False, default="")
    image_hash = Column(String(64), nullable=False, index=True)
    center_score = Column(Float, default=0.0)
    chinese_score = Column(Float, default=0.0)
    quality_score = Column(Float, default=0.0)
    detail_score = Column(Float, default=0.0)
    selected = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
