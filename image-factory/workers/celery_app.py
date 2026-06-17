from __future__ import annotations

from celery import Celery

from configs.settings import settings

celery_app = Celery(
    "image_factory",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "tasks.generation",
        "tasks.delivery",
        "tasks.product",
        "tasks.intelligence",
    ],
)

celery_app.conf.update(
    task_acks_late=settings.celery_task_acks_late,
    task_reject_on_worker_lost=settings.celery_task_reject_on_worker_lost,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    worker_concurrency=settings.celery_worker_concurrency,
)

celery_app.conf.beat_schedule = {
    "daily-trend-report": {
        "task": "tasks.intelligence.generate_daily_trend_report",
        "schedule": 86400.0,
        "kwargs": {},
    },
    "weekly-trend-report": {
        "task": "tasks.intelligence.generate_weekly_trend_report",
        "schedule": 604800.0,
        "kwargs": {},
    },
    "health-report": {
        "task": "tasks.intelligence.generate_health_report",
        "schedule": 3600.0,
        "kwargs": {},
    },
    "session-maintenance": {
        "task": "tasks.intelligence.maintain_sessions",
        "schedule": 1800.0,
        "kwargs": {},
    },
    "captcha-report": {
        "task": "tasks.intelligence.generate_captcha_report",
        "schedule": 86400.0,
        "kwargs": {},
    },
    "session-cleanup": {
        "task": "tasks.intelligence.cleanup_stale_sessions",
        "schedule": 43200.0,
        "kwargs": {},
    },
    "opportunity-report": {
        "task": "tasks.intelligence.generate_marketplace_opportunity_report",
        "schedule": 86400.0,
        "kwargs": {},
    },
}
