from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Boolean

from database.session import Base


class FeatureCache(Base):
    __tablename__ = "feature_cache"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_hash = Column(String(64), nullable=False, unique=True, index=True)
    center_score = Column(Float, default=0.0)
    chinese_score = Column(Float, default=0.0)
    quality_score = Column(Float, default=0.0)
    detail_score = Column(Float, default=0.0)
    ocr_detected = Column(Boolean, default=False)
    selected_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
