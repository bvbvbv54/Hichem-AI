from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from database.session import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
