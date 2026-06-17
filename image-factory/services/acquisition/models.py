from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FailureType(str, Enum):
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CAPTCHA = "captcha"
    AUTH_REQUIRED = "auth_required"
    PAGE_STRUCTURE_CHANGED = "page_structure_changed"
    BOT_BLOCKED = "bot_blocked"
    ROBOTS_DISALLOWED = "robots_disallowed"


@dataclass
class AcquisitionJob:
    job_id: str
    url: str
    max_images: int = 10
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    attempts: int = 0
    last_error: str | None = None
    checkpoint: dict = field(default_factory=dict)


@dataclass
class AcquisitionResult:
    job_id: str
    url: str
    success: bool
    image_paths: list[str] = field(default_factory=list)
    image_hashes: list[str] = field(default_factory=list)
    page_title: str = ""
    page_description: str = ""
    failure_type: FailureType | None = None
    failure_detail: str | None = None
    duration_ms: float = 0
    was_cached: bool = False
    required_browser: bool = False
