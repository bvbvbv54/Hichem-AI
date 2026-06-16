from __future__ import annotations

import enum


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    ENHANCING_PROMPT = "enhancing_prompt"
    GENERATING = "generating"
    STORING = "storing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobType(str, enum.Enum):
    SINGLE = "single"
    BULK = "bulk"
    SCHEDULED = "scheduled"


class ImageProvider(str, enum.Enum):
    REPLICATE = "replicate"
    STABILITYAI = "stabilityai"
    OPENAI = "openai"


class TemplateCategory(str, enum.Enum):
    PRODUCT_MOCKUP = "product_mockup"
    LIFESTYLE = "lifestyle"
    MARKETING_BANNER = "marketing_banner"
    BLOG_THUMBNAIL = "blog_thumbnail"
    INSTAGRAM_CREATIVE = "instagram_creative"
    LINKEDIN_CREATIVE = "linkedin_creative"
    YOUTUBE_THUMBNAIL = "youtube_thumbnail"
    LANDING_PAGE = "landing_page"
    FEATURE_ILLUSTRATION = "feature_illustration"
    MARKETING_ASSET = "marketing_asset"
    CUSTOM = "custom"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
