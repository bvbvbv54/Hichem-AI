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
