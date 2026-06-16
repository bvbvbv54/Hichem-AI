from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCode(str, Enum):
    ACQ_RATE_LIMITED = "ACQ_001"
    ACQ_CAPTCHA = "ACQ_002"
    ACQ_BOT_BLOCKED = "ACQ_003"
    ACQ_ROBOTS_DISALLOWED = "ACQ_004"
    ACQ_NO_IMAGES_FOUND = "ACQ_005"
    ACQ_ALL_IMAGES_INVALID = "ACQ_006"
    ACQ_TIMEOUT = "ACQ_007"
    ACQ_NETWORK_ERROR = "ACQ_008"

    OCR_GEMINI_QUOTA = "OCR_001"
    OCR_GEMINI_UNAVAILABLE = "OCR_002"
    OCR_PARSE_FAILED = "OCR_003"
    TRANS_FAILED = "OCR_004"

    S1_GEMINI_QUOTA = "S1_001"
    S1_GEMINI_UNAVAILABLE = "S1_002"
    S1_PARSE_FAILED = "S1_003"
    S1_NO_IMAGES = "S1_004"

    S2_GENERATION_FAILED = "S2_001"
    S2_NANOBANA_QUOTA = "S2_002"
    S2_NANOBANA_UNAVAILABLE = "S2_003"
    S2_ALL_BELOW_THRESHOLD = "S2_004"
    S2_RANKING_FAILED = "S2_005"

    DRIVE_NOT_AUTH = "GD_001"
    DRIVE_UPLOAD_FAILED = "GD_002"
    DRIVE_QUOTA_EXCEEDED = "GD_003"
    DRIVE_FOLDER_ERROR = "GD_004"

    SYS_DB_WRITE_FAILED = "SYS_001"
    SYS_REDIS_UNAVAILABLE = "SYS_002"
    SYS_CELERY_WORKER_DOWN = "SYS_003"

    UNKNOWN = "UNK_000"


@dataclass
class PipelineError:
    code: ErrorCode
    severity: ErrorSeverity
    message: str
    technical_detail: str = ""
    job_id: str = ""
    product_url: str = ""
    stage: str = ""
    retryable: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)
    context: dict = field(default_factory=dict)
