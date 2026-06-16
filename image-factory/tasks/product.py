from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from workers.celery_app import celery_app
from workers.async_runner import run_async
from configs.settings import settings
from configs.logging import get_logger
from database.session import async_session
from database.repository import JobRepository
from models.enums import JobStatus
from services.event_bus import publish, EventType, PipelineEvent
from services.time_estimator import TimeEstimator

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_single_product(self, job_id: str, url: str, project_name: str = ""):
    logger.info("processing_single_product", job_id=job_id, url=url)
    try:
        run_async(_execute_product_pipeline(self, job_id, url, project_name))
    except Exception as exc:
        logger.error("product_pipeline_crash", job_id=job_id, error=str(exc))
        run_async(_mark_job_failed(job_id, str(exc)))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=30)
def process_product_batch(self, batch_id: str, product_list: list[dict]):
    logger.info("processing_product_batch", batch_id=batch_id, count=len(product_list))
    run_async(_execute_batch_dispatch(self, batch_id, product_list))


async def _execute_batch_dispatch(self: Any, batch_id: str, product_list: list[dict]):
    import redis.asyncio as aioredis
    redis_conn = await aioredis.from_url(settings.redis_url)

    try:
        product_list.sort(key=lambda p: p.get("priority", 0), reverse=True)
        total = len(product_list)
        completed_count = 0
        failed_count = 0
        dispatched = 0
        sem = asyncio.Semaphore(settings.batch_max_concurrent)

        progress_key = f"batch:{batch_id}:progress"
        paused_key = f"batch:{batch_id}:paused"

        async def dispatch_one(product: dict):
            nonlocal dispatched, completed_count, failed_count
            async with sem:
                is_paused = await redis_conn.get(paused_key)
                if is_paused:
                    logger.info("batch_paused_waiting", batch_id=batch_id)
                    while await redis_conn.get(paused_key):
                        await asyncio.sleep(5)
                    logger.info("batch_resumed", batch_id=batch_id)

                job_id = product["job_id"]
                url = product["url"]
                celery_app.send_task("tasks.product.process_single_product", args=[job_id, url, ""])
                dispatched += 1

                await redis_conn.hincrby(progress_key, "dispatched", 1)
                if dispatched % 5 == 0:
                    await _publish_batch_progress(batch_id, progress_key, redis_conn)

        tasks = [dispatch_one(p) for p in product_list]
        await asyncio.gather(*tasks)

        track_key = f"batch:{batch_id}:track"
        final = await redis_conn.hgetall(track_key) or {}
        completed_count = int(final.get(b"completed", final.get("completed", 0)))
        failed_count = int(final.get(b"failed", final.get("failed", 0)))

        await _publish_batch_progress(batch_id, progress_key, redis_conn)

        async with async_session() as session:
            repo = JobRepository(session)
            final_status = JobStatus.COMPLETED.value if failed_count == 0 else JobStatus.PARTIALLY_COMPLETED.value
            await repo.update(batch_id, {
                "status": final_status,
                "progress": 100.0,
                "completed_at": datetime.utcnow(),
                "meta": {
                    "total": total,
                    "dispatched": dispatched,
                    "completed": completed_count,
                    "failed": failed_count,
                    "paused": False,
                },
            })

        logger.info("batch_dispatch_complete", batch_id=batch_id, total=total, completed=completed_count, failed=failed_count)

    finally:
        await redis_conn.delete(f"batch:{batch_id}:progress")
        await redis_conn.delete(f"batch:{batch_id}:paused")
        await redis_conn.delete(f"batch:{batch_id}:track")
        await redis_conn.aclose()


async def _publish_batch_progress(batch_id: str, progress_key: str, redis_conn: Any):
    progress_data = await redis_conn.hgetall(progress_key) or {}
    dispatched = int(progress_data.get(b"dispatched", progress_data.get("dispatched", 0)))

    track_key = f"batch:{batch_id}:track"
    track_data = await redis_conn.hgetall(track_key) or {}
    completed = int(track_data.get(b"completed", track_data.get("completed", 0)))
    failed = int(track_data.get(b"failed", track_data.get("failed", 0)))

    await publish(PipelineEvent(
        event_type=EventType.BATCH_PROGRESS,
        job_id=batch_id,
        data={
            "batch_id": batch_id,
            "total": dispatched,
            "completed": completed,
            "failed": failed,
            "ts": datetime.utcnow().isoformat(),
        },
    ))


async def _execute_product_pipeline(self: Any, job_id: str, url: str, project_name: str):
    import redis.asyncio as redis_async
    redis_conn = await redis_async.from_url(settings.redis_url)

    try:
        estimator = TimeEstimator(redis_conn)

        async with async_session() as session:
            repo = JobRepository(session)
            await repo.update_status(job_id, JobStatus.PROCESSING)

        from services.acquisition import AcquisitionPipeline, AcquisitionJob
        from services.pipeline import Stage1Analyzer, Stage2Generator
        from services.storage.local import LocalStorage
        from services.admin_notifier import get_notifier

        get_notifier(redis_conn)
        storage = LocalStorage()
        acquisition = AcquisitionPipeline()
        stage1 = Stage1Analyzer(redis_conn)
        stage2 = Stage2Generator()

        failure_type = None
        failure_detail = None
        drive_folder_url = None
        parent_batch_id = None

        # Fetch parent batch ID early for error tracking
        parent_batch_id = await _get_parent_batch_id(job_id)

        try:
            # Stage 1: Acquisition
            stage_start = time.monotonic()
            await _publish_stage_event(job_id, "acquiring_images", "Downloading product images")

            acq_job = AcquisitionJob(job_id=job_id, url=url, max_images=5)
            acq_result = await acquisition.run(acq_job)

            if not acq_result.success or not acq_result.image_paths:
                failure_type = "acquisition"
                failure_detail = acq_result.failure_detail or "No images acquired"
                raise RuntimeError(failure_detail)

            await estimator.record_stage(job_id, "acquisition", time.monotonic() - stage_start)

            # Stage 2: AI Analysis
            stage_start = time.monotonic()
            await _publish_stage_event(job_id, "analyzing_images", "Analyzing product with AI")

            product_spec = await stage1.analyze(acq_result.image_paths, url)

            if product_spec.translated_labels:
                await _publish_stage_event(job_id, "translating_labels", "Localizing labels")
                await estimator.record_stage(job_id, "translation", time.monotonic() - stage_start)

            # Stage 3: Generation
            stage_start = time.monotonic()
            await _publish_stage_event(job_id, "generating_images", "Generating localized images")

            from services.pipeline import GenerationPlan

            plan = GenerationPlan(
                product_spec=product_spec,
                reference_image_paths=acq_result.image_paths,
                output_count=min(3, len(acq_result.image_paths)),
                style_directive="American e-commerce, white background, studio lighting",
                negative_prompt=(
                    "chinese text, chinese characters, blurry, watermark, low quality, "
                    "distorted proportions, missing parts, extra objects, busy background, "
                    "dark background, shadows on product, reflections on product"
                ),
            )

            generated_assets = await stage2.generate(plan, job_id)
            if not generated_assets:
                failure_type = "ai"
                failure_detail = "AI generation produced no outputs"
                raise RuntimeError(failure_detail)

            await estimator.record_stage(job_id, "generation", time.monotonic() - stage_start)

            # Stage 4: Save locally
            output_dir = Path(settings.storage_path) / project_name / job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            selected_paths: list[str] = []
            for asset in generated_assets:
                if asset.selected:
                    dst = output_dir / Path(asset.local_path).name
                    import shutil
                    shutil.copy2(asset.local_path, str(dst))
                    selected_paths.append(str(dst))

            result_data = {
                "job_id": job_id,
                "url": url,
                "product_name": product_spec.product_name,
                "images_selected": len(selected_paths),
                "selected_assets": selected_paths,
            }

            # Stage 5: Google Drive
            stage_start = time.monotonic()
            if settings.google_drive_auto_upload and selected_paths:
                try:
                    await _publish_stage_event(job_id, "saving_to_drive", "Saving to Google Drive")
                    from services.storage.google_drive import get_drive_manager
                    gdrive = get_drive_manager()
                    if await gdrive.authenticate():
                        upload_result = await gdrive.upload_product_outputs(
                            product_name=product_spec.product_name or f"job_{job_id}",
                            file_paths=selected_paths,
                            root_folder_name=settings.google_drive_root_folder,
                        )
                        drive_folder_url = upload_result.get("folder_url")
                        result_data["drive_folder_url"] = drive_folder_url

                        await publish(PipelineEvent(
                            event_type=EventType.DRIVE_SAVED,
                            job_id=job_id,
                            data={"folder_url": drive_folder_url},
                        ))
                    await estimator.record_stage(job_id, "drive_upload", time.monotonic() - stage_start)
                except Exception as e:
                    failure_type = "drive"
                    failure_detail = str(e)
                    logger.warning("drive_upload_failed", job_id=job_id, error=str(e))

            # Finalize
            meta = {
                **result_data,
                "url": url,
                "product_name": product_spec.product_name or "",
                "drive_folder_url": drive_folder_url or "",
            }
            async with async_session() as session:
                repo = JobRepository(session)
                await repo.update(job_id, {
                    "meta": meta,
                    "completed_at": datetime.utcnow(),
                })

            await _publish_stage_event(job_id, "completed", "Complete")
            await _update_job_status(job_id, JobStatus.COMPLETED, progress=100.0)

            await publish(PipelineEvent(
                event_type=EventType.JOB_COMPLETED,
                job_id=job_id,
                data={
                    "url": url,
                    "product_name": product_spec.product_name or "",
                    "drive_folder_url": drive_folder_url or "",
                },
            ))

            # Track batch progress
            if parent_batch_id:
                track_key = f"batch:{parent_batch_id}:track"
                await redis_conn.hincrby(track_key, "completed", 1)

            await estimator.record_stage(job_id, "total_product", time.monotonic() - (await _get_job_start_time(job_id, redis_conn)))

            logger.info("product_completed", job_id=job_id, url=url, images=len(selected_paths))

        except Exception as exc:
            if failure_type is None:
                failure_type = "acquisition"
                failure_detail = str(exc)

            await _publish_stage_event(job_id, "failed", f"Failed: {failure_detail}")

            try:
                retries_left = self.max_retries - self.request.retries if hasattr(self, "max_retries") else 0
            except Exception:
                retries_left = 0

            if retries_left > 0:
                backoff = int(60 * math.pow(2, self.request.retries))
                logger.info("product_retrying", job_id=job_id, url=url, retry=self.request.retries, backoff=backoff)
                await _publish_stage_event(job_id, "retrying", f"Retrying in {backoff}s")
                raise self.retry(exc=exc, countdown=backoff)

            await _mark_job_failed(job_id, failure_detail, failure_type)

            if parent_batch_id:
                track_key = f"batch:{parent_batch_id}:track"
                await redis_conn.hincrby(track_key, "failed", 1)

            await publish(PipelineEvent(
                event_type=EventType.JOB_FAILED,
                job_id=job_id,
                data={
                    "url": url,
                    "failure_type": failure_type or "unknown",
                    "failure_detail": failure_detail or str(exc),
                },
            ))

            logger.error("product_failed", job_id=job_id, url=url, type=failure_type, detail=str(exc))

        finally:
            await acquisition.close()

    finally:
        await redis_conn.aclose()


async def _get_job_meta(job_id: str) -> dict | None:
    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        return job.meta if job else None


async def _get_parent_batch_id(job_id: str) -> str | None:
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Job.parent_job_id).where(Job.id == job_id))
        row = result.one_or_none()
        return row[0] if row else None


async def _get_job_start_time(job_id: str, redis_conn: Any) -> float:
    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if job and job.created_at:
            return (datetime.utcnow() - job.created_at).total_seconds()
        return 0.0


async def _publish_stage_event(job_id: str, stage: str, message: str):
    await publish(PipelineEvent(
        event_type=EventType.JOB_STAGE_CHANGED,
        job_id=job_id,
        data={"stage": stage, "message": message},
    ))
    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        existing_meta = dict(job.meta or {}) if job else {}
        existing_meta.update({"stage": stage, "stage_message": message})
        await repo.update(job_id, {"meta": existing_meta})


async def _update_job_status(job_id: str, status: JobStatus, **extra):
    async with async_session() as session:
        repo = JobRepository(session)
        await repo.update_status(job_id, status, **extra)


async def _mark_job_failed(job_id: str, error_message: str, failure_type: str = "unknown"):
    async with async_session() as session:
        repo = JobRepository(session)
        await repo.update_status(job_id, JobStatus.FAILED, error_message=error_message, meta={"failure_type": failure_type})
