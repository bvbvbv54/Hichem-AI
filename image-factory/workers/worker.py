"""
Worker entry point for Celery.
Run with: celery -A workers.worker worker --loglevel=info --concurrency=4
"""
from workers.celery_app import celery_app  # noqa: F401 — exposes `app` for CLI
