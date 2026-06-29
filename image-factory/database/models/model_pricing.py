from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, JSON, String, Text
from database.session import Base


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    provider = Column(String(64), nullable=False, default="google")

    # Pricing model type
    pricing_model = Column(String(32), nullable=False, default="token_based")

    # Token-based pricing (Nano Banana)
    input_token_cost_per_million = Column(Float, nullable=False, default=0.0)
    output_token_cost_per_million = Column(Float, nullable=False, default=0.0)
    input_image_tokens = Column(Integer, nullable=False, default=0)
    output_tokens_by_resolution = Column(JSON, nullable=False, default=dict)
    default_resolution = Column(String(32), nullable=False, default="1024")

    # Flat-rate / input-output pricing (Imagen)
    cost_per_output_image = Column(Float, nullable=False, default=0.0)
    cost_per_reference_image = Column(Float, nullable=False, default=0.0)

    # Deprecation lifecycle
    deprecated = Column(Boolean, nullable=False, default=False)
    deprecation_date = Column(Date, nullable=True)
    deprecation_message = Column(Text, default="")
    sunset_date = Column(Date, nullable=True)

    # Price source metadata
    price_source_url = Column(Text, default="")
    price_checked_date = Column(Date, nullable=True)

    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
