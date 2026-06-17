from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, update as sql_update

from workers.celery_app import celery_app
from workers.async_runner import run_async
from configs.settings import settings
from configs.logging import get_logger
from database.session import async_session
from database.repository import JobRepository
from database.models.job import Job
from database.models.product_link import ProductLink
from models.enums import JobStatus
from services.event_bus import publish, EventType, PipelineEvent
from services.time_estimator import TimeEstimator

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
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


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r'\s+', "_", name)
    return name.strip("._ ")[:100] or "product"


def _resolve_output_dir(product_name: str) -> Path:
    name_dir = _sanitize_filename(product_name) if product_name else "product"
    base = settings.storage_path
    output_dir = base / name_dir
    return output_dir


async def _execute_product_pipeline(self: Any, job_id: str, url: str, project_name: str):
    import redis.asyncio as redis_async
    redis_conn = await redis_async.from_url(settings.redis_url)

    orchestrator: Any = None

    try:
        estimator = TimeEstimator(redis_conn)

        async with async_session() as session:
            repo = JobRepository(session)
            await repo.update_status(job_id, JobStatus.PROCESSING)

        from services.acquisition import AcquisitionPipeline, AcquisitionJob
        from services.storage.local import LocalStorage
        from services.admin_notifier import get_notifier
        from services.intelligence.orchestrator import IntelligenceOrchestrator
        from services.intelligence.models import ChallengeType, IntelligenceEventType

        get_notifier()
        storage = LocalStorage()
        acquisition = AcquisitionPipeline()
        orchestrator = IntelligenceOrchestrator()

        failure_type = None
        failure_detail = None
        parent_batch_id = None
        session_id = ""

        parent_batch_id = await _get_parent_batch_id(job_id)

        try:
            await _update_product_link_status(url, "scraping", job_id=job_id)

            # Intelligence: prepare session and request context
            domain, marketplace, ctx = await orchestrator.prepare_request(url)
            session_id = ctx["session"].id

            stage_start = time.monotonic()
            await _publish_stage_event(job_id, "acquiring_images", "Downloading product images")

            acq_job = AcquisitionJob(job_id=job_id, url=url, max_images=5)
            acq_result = await acquisition.run(acq_job)

            duration_ms = (time.monotonic() - stage_start) * 1000

            if not acq_result.success or not acq_result.image_paths:
                failure_type = "acquisition"
                failure_detail = acq_result.failure_detail or "No images acquired"

                was_captcha = acq_result.failure_type in ("captcha",)
                was_blocked = acq_result.failure_type in ("bot_blocked", "rate_limited")
                if acq_result.failure_type == "captcha" and acq_result.required_browser:
                    await orchestrator.captcha_manager.record_event(
                        domain=domain,
                        session_id=session_id,
                        url=url,
                        challenge_type=ChallengeType.CAPTCHA,
                        html=acq_result.failure_detail or "",
                        marketplace=marketplace,
                    )
                await orchestrator.record_failure(
                    url=url,
                    failure_type=failure_type,
                    was_captcha=was_captcha,
                    was_blocked=was_blocked,
                    duration_ms=duration_ms,
                    html=acq_result.failure_detail or "",
                    session_id=session_id,
                )
                if acq_result.failure_type == "captcha":
                    await orchestrator.session_manager.record_failure(ctx["session"], "captcha")
                elif acq_result.failure_type == "bot_blocked":
                    await orchestrator.session_manager.record_failure(ctx["session"], "blocked")

                await _update_product_link_status(url, "failed", error_message=failure_detail, failure_type=failure_type)
                raise RuntimeError(failure_detail)

            await orchestrator.record_success(url, extracted=True, duration_ms=duration_ms)
            await orchestrator.session_manager.record_success(ctx["session"], extracted=True)

            scraped_count = len(acq_result.image_paths)
            product_name = acq_result.page_title or Path(urlparse(url).path).stem.replace("-", " ").replace("_", " ").title() or url
            product_description = acq_result.page_description

            await _update_product_link_status(url, "scraped", product_name=product_name, scraped_image_count=scraped_count)

            await estimator.record_stage(job_id, "acquisition", time.monotonic() - stage_start)

            output_dir = _resolve_output_dir(product_name)
            images_dir = output_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            saved_paths: list[str] = []
            import shutil
            for img_path in acq_result.image_paths:
                dst = images_dir / Path(img_path).name
                shutil.copy2(img_path, str(dst))
                saved_paths.append(str(dst))

            if product_description:
                desc_path = output_dir / "description.json"
                desc_path.write_text(json.dumps({
                    "product_name": product_name,
                    "description": product_description,
                    "url": url,
                    "job_id": job_id,
                    "scraped_at": datetime.utcnow().isoformat(),
                }, indent=2))

            # Intelligence: add product to knowledge graph
            try:
                await orchestrator.add_to_knowledge_graph(
                    name=product_name,
                    marketplace=marketplace,
                    url=url,
                    attributes={
                        "description": product_description,
                        "image_count": scraped_count,
                        "job_id": job_id,
                    },
                    image_hashes=[h for h in acq_result.image_hashes if h],
                )
            except Exception as kg_error:
                logger.warning("knowledge_graph_update_failed", job_id=job_id, error=str(kg_error))

            result_data = {
                "job_id": job_id,
                "url": url,
                "product_name": product_name,
                "product_description": product_description,
                "images_scraped": len(saved_paths),
                "saved_assets": saved_paths,
                "output_directory": str(output_dir),
                "stage": "scraped_only",
                "marketplace": marketplace,
                "session_id": session_id,
            }

            meta = {
                **result_data,
                "url": url,
                "product_name": product_name,
            }
            async with async_session() as session:
                repo = JobRepository(session)
                await repo.update(job_id, {
                    "meta": meta,
                    "completed_at": datetime.utcnow(),
                })

            await _publish_stage_event(job_id, "completed", "Scraping complete - no AI generation")
            await _update_job_status(job_id, JobStatus.COMPLETED, progress=100.0)

            await publish(PipelineEvent(
                event_type=EventType.JOB_COMPLETED,
                job_id=job_id,
                data={
                    "url": url,
                    "product_name": product_name,
                    "stage": "scraped_only",
                    "marketplace": marketplace,
                },
            ))

            if parent_batch_id:
                track_key = f"batch:{parent_batch_id}:track"
                await redis_conn.hincrby(track_key, "completed", 1)

            await estimator.record_stage(job_id, "total_product", time.monotonic() - (await _get_job_start_time(job_id, redis_conn)))

            logger.info("product_scraped", job_id=job_id, url=url, images=len(saved_paths),
                product_name=product_name, marketplace=marketplace)

        except Exception as exc:
            if failure_type is None:
                failure_type = "acquisition"
                failure_detail = str(exc)

            await _update_product_link_status(url, "failed" if failure_type != "acquisition" else "error",
                error_message=failure_detail or str(exc),
                failure_type=failure_type or "unknown",
            )

            await _publish_stage_event(job_id, "failed", f"Failed: {failure_detail}")

            try:
                retries_left = self.max_retries - self.request.retries if hasattr(self, "max_retries") else 0
            except Exception:
                retries_left = 0

            non_retryable = False
            if failure_detail:
                fd = failure_detail.lower()
                if any(kw in fd for kw in ["captcha", "no image urls", "no images acquired"]):
                    non_retryable = True
            if non_retryable:
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
        if orchestrator:
            try:
                await orchestrator.browser_pool.close()
            except Exception:
                pass


async def _update_product_link_status(url: str, status: str, **extra):
    try:
        async with async_session() as session:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            result = await session.execute(select(ProductLink).where(ProductLink.url_hash == url_hash))
            link = result.scalar_one_or_none()
            if link:
                updates = {"status": status, "updated_at": datetime.utcnow(), **extra}
                if status in ("completed", "failed", "error"):
                    updates["completed_at"] = datetime.utcnow()
                if status == "scraped":
                    updates["last_scraped_at"] = datetime.utcnow()
                if status == "generating" or status == "completed":
                    updates["last_generated_at"] = datetime.utcnow()
                await session.execute(
                    sql_update(ProductLink).where(ProductLink.id == link.id).values(**updates)
                )
                await session.commit()
    except Exception as e:
        logger.warning("failed_to_update_product_link", url=url, error=str(e))


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
