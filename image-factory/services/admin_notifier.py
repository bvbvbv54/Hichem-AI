from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from services.pipeline.errors import PipelineError, ErrorSeverity, ErrorCode
from services.event_bus import publish, EventType, PipelineEvent
from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_TO_EVENT = {
    ErrorSeverity.INFO: EventType.JOB_STAGE_CHANGED,
    ErrorSeverity.WARNING: EventType.SYSTEM_ALERT,
    ErrorSeverity.ERROR: EventType.JOB_FAILED,
    ErrorSeverity.CRITICAL: EventType.SYSTEM_ALERT,
}

_LOG_FN = {
    ErrorSeverity.INFO: logger.info,
    ErrorSeverity.WARNING: logger.warning,
    ErrorSeverity.ERROR: logger.error,
    ErrorSeverity.CRITICAL: logger.critical,
}


class AdminNotifier:
    def __init__(self) -> None:
        pass

    async def notify(self, error: PipelineError) -> None:
        try:
            log_fn = _LOG_FN.get(error.severity, logger.error)
            log_fn(
                "pipeline_error",
                code=error.code.value,
                severity=error.severity.value,
                stage=error.stage,
                job_id=error.job_id,
                message=error.message,
                retryable=error.retryable,
            )

            event_type = _SEVERITY_TO_EVENT.get(error.severity, EventType.SYSTEM_ALERT)
            await publish(PipelineEvent(
                event_type=event_type,
                job_id=error.job_id,
                data={
                    "error_code": error.code.value,
                    "severity": error.severity.value,
                    "stage": error.stage,
                    "message": error.message,
                    "retryable": error.retryable,
                    "product_url": error.product_url,
                },
            ))

            r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
            try:
                notification: dict[str, Any] = {
                    "id": f"{error.job_id}:{error.code.value}:{int(error.timestamp.timestamp())}",
                    "code": error.code.value,
                    "severity": error.severity.value,
                    "message": error.message,
                    "stage": error.stage,
                    "job_id": error.job_id,
                    "retryable": error.retryable,
                    "timestamp": error.timestamp.isoformat(),
                }
                await r.lpush("admin:notifications", json.dumps(notification))
                await r.ltrim("admin:notifications", 0, 499)
                await r.expire("admin:notifications", 604800)
            finally:
                await r.aclose()
        except Exception as e:
            logger.error("admin_notifier_failed", exception=str(e))

    async def notify_critical(self, message: str, detail: str = "", context: dict | None = None) -> None:
        await self.notify(PipelineError(
            code=ErrorCode.UNKNOWN,
            severity=ErrorSeverity.CRITICAL,
            message=message,
            technical_detail=detail,
            context=context or {},
        ))

    async def close(self) -> None:
        pass


_notifier_instance: AdminNotifier | None = None


def get_notifier(redis_client: Any = None) -> AdminNotifier:
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = AdminNotifier()
    return _notifier_instance
