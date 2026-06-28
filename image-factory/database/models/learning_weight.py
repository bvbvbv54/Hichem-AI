from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from database.session import Base


class LearningWeight(Base):
    __tablename__ = "learning_weights"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scope_id = Column(String(36), nullable=False, default="")
    scope_type = Column(String(16), nullable=False, default="global")
    center_weight = Column(Float, default=0.30)
    chinese_weight = Column(Float, default=0.30)
    detail_weight = Column(Float, default=0.20)
    quality_weight = Column(Float, default=0.20)
    event_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("scope_id", "scope_type", name="uq_scope"),
    )
