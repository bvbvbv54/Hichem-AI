from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, JSON, Boolean

from database.session import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True, default="")
    type = Column(String(64), nullable=False, default="info")
    level = Column(String(16), nullable=False, default="info")
    title = Column(String(255), nullable=False)
    message = Column(Text, default="")
    project_id = Column(String(36), nullable=True, default="")
    run_id = Column(String(36), nullable=True, default="")
    data = Column(JSON, default=dict)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
