from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import celery.exceptions
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
from services.notifications import send_notification, NotificationLevel
from PIL import Image as PILImage

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, soft_time_limit=600, time_limit=660, acks_late=True)
def process_single_product(self, job_id: str, url: str, project_name: str = ""):
    logger.info("processing_single_product", job_id=job_id, url=url)
    try:
        run_async(_execute_product_pipeline(self, job_id, url, project_name))
    except celery.exceptions.Retry:
        raise
    except Exception as exc:
        logger.error("product_pipeline_crash", job_id=job_id, error=str(exc))
        run_async(_mark_job_failed(job_id, str(exc)))
        run_async(_update_product_link_status(url, "error", error_message=f"Task crashed: {str(exc)[:200]}"))


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


from services.utils import sanitize_filename


def _resolve_output_dir(product_name: str) -> Path:
    name_dir = sanitize_filename(product_name, max_length=100) if product_name else "product"
    base = settings.storage_path
    user_dir = settings.google_drive_root_folder
    if user_dir:
        base = base / _sanitize_filename(user_dir)
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
        from services.storage.r2 import get_r2_storage
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
            from services.acquisition.pipeline import BANNED_DOMAINS
            domain = urlparse(url).netloc.replace("www.", "")
            if any(d in domain for d in BANNED_DOMAINS):
                logger.warning("domain_banned_at_task", job_id=job_id, url=url, domain=domain)
                failure_type = "domain_banned"
                failure_detail = f"{domain} is not supported — permanently banned (login wall / CAPTCHA / no anonymous access)"
                raise RuntimeError(failure_detail)

            # Track scrape attempts to prevent infinite crash loops
            await _increment_scrape_attempt(url)
            scrape_meta = await _get_product_link_meta(url)
            if scrape_meta:
                attempts = scrape_meta.get("scrape_attempts", 0)
                if attempts >= 3:
                    msg = f"Permanently failed after {attempts} consecutive scrape attempts"
                    await _update_product_link_status(url, "error", error_message=msg, failure_type="max_attempts_exceeded")
                    raise RuntimeError(msg)

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

            from services.translation_service import detect_language, needs_translation, translate_text
            source_title = product_name
            source_language = detect_language(source_title)
            if needs_translation(source_title):
                display_title = await translate_text(source_title)
            else:
                display_title = source_title

            await _update_product_link_status(
                url, "scraped",
                product_name=product_name,
                display_title=display_title,
                source_title=source_title,
                source_language=source_language,
            )

            await estimator.record_stage(job_id, "acquisition", time.monotonic() - stage_start)

            output_dir = _resolve_output_dir(product_name)
            scraped_dir = output_dir / "scraped"
            scraped_dir.mkdir(parents=True, exist_ok=True)

            saved_paths: list[str] = []
            import shutil
            seen_dst: set[str] = set()
            for img_path in acq_result.image_paths:
                if not Path(img_path).exists():
                    logger.warning("source_image_missing", path=img_path)
                    continue
                dst = str(scraped_dir / Path(img_path).name)
                if dst not in seen_dst:
                    seen_dst.add(dst)
                    shutil.copy2(img_path, dst)
                    saved_paths.append(dst)

            deduped_count = len(saved_paths)
            await _update_product_link_status(url, "scraped", scraped_image_count=deduped_count)

            # Upload scraped images to Cloudflare R2 (primary storage)
            r2_results: list[dict] = []
            product_link_id = await _get_product_link_id(url)
            try:
                r2 = get_r2_storage()
                for idx, sp in enumerate(saved_paths):
                    sp_path = Path(sp)
                    if not sp_path.exists():
                        continue
                    r2_result = await r2.upload_file(
                        local_path=sp_path,
                        project_id=project_name or "default",
                        product_id=product_link_id or job_id,
                        category="scraped",
                    )
                    r2_results.append(r2_result)
                    # Register URL→R2 key cache for future scrapes
                    if idx < len(acq_result.image_urls):
                        try:
                            await r2.register_url_cache(acq_result.image_urls[idx], r2_result["key"])
                        except Exception as cache_err:
                            logger.debug("r2_cache_register_skipped", error=str(cache_err))
                logger.info("r2_scraped_uploaded", product=product_name, count=len(r2_results))
            except Exception as r2_err:
                logger.warning("r2_scraped_upload_failed", error=str(r2_err))

            # Fix: create Asset records for each kept image so detail page can find them
            if saved_paths:
                async with async_session() as asset_session:
                    from database.repository import AssetRepository
                    asset_repo = AssetRepository(asset_session)
                    for idx, sp in enumerate(saved_paths):
                        sp_path = Path(sp)
                        if not sp_path.exists():
                            continue
                        try:
                            from PIL import Image as PILImg
                            with PILImg.open(sp_path) as img:
                                width, height = img.size
                        except Exception:
                            width = height = 0
                        try:
                            file_size = sp_path.stat().st_size
                        except Exception:
                            file_size = 0
                        ext = sp_path.suffix.lower().lstrip(".")
                        mime = f"image/{ext}" if ext else "image/png"
                        asset_meta = {"type": "scraped"}
                        if idx < len(r2_results):
                            asset_meta["r2_url"] = r2_results[idx]["url"]
                            asset_meta["r2_key"] = r2_results[idx]["key"]
                        await asset_repo.create({
                            "id": str(uuid.uuid4()),
                            "job_id": job_id,
                            "filename": sp_path.name,
                            "file_path": str(sp_path),
                            "file_size": file_size,
                            "mime_type": mime.replace("jpg", "jpeg"),
                            "width": width,
                            "height": height,
                            "alt_text": product_name or "",
                            "meta": asset_meta,
                        })

            if deduped_count == 0:
                failure_type = "acquisition"
                failure_detail = "All images removed by dedup"
                await _update_product_link_status(url, "failed", error_message=failure_detail, failure_type=failure_type)
                raise RuntimeError(failure_detail)

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

            # Google Drive auto-upload
            drive_folder_url = ""
            if settings.google_drive_auto_upload and saved_paths:
                try:
                    sa_dir = Path(settings.google_drive_credentials_path).parent
                    sa_path = sa_dir / "service_account.json"
                    if sa_path.exists():
                        from services.storage.google_drive import get_drive_manager
                        mgr = get_drive_manager()
                        authed = await mgr.use_service_account(str(sa_path))
                        if authed:
                            up_result = await mgr.upload_product_outputs(
                                product_name=product_name,
                                file_paths=saved_paths,
                                root_folder_name=settings.google_drive_root_folder,
                            )
                            drive_folder_url = up_result.get("folder_url", "")
                            logger.info("drive_auto_uploaded", product=product_name, url=drive_folder_url, files=len(saved_paths))
                            await publish(PipelineEvent(
                                event_type=EventType.DRIVE_SAVED,
                                job_id=job_id,
                                data={"product_name": product_name, "folder_url": drive_folder_url, "file_count": len(saved_paths)},
                            ))
                            await send_notification(
                                user_id="",
                                title="Drive: Images Saved",
                                message=f"{len(saved_paths)} images for '{product_name}' uploaded to Google Drive",
                                event_type="drive_saved",
                                level=NotificationLevel.SUCCESS,
                                data={"product_name": product_name, "folder_url": drive_folder_url, "file_count": len(saved_paths)},
                            )
                except Exception as drv_err:
                    logger.warning("drive_auto_upload_failed", job_id=job_id, error=str(drv_err))

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
                "drive_folder_url": drive_folder_url,
            }

            meta = {
                **result_data,
                "url": url,
                "product_name": product_name,
                "drive_folder_url": drive_folder_url,
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

            link_project_id = await _get_product_link_project_id(url) or project_name
            await _check_project_completion(link_project_id, project_name)

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
            if failure_type == "domain_banned":
                non_retryable = True
            if failure_detail and not non_retryable:
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

            link_project_id = await _get_product_link_project_id(url) or project_name
            await _check_project_completion(link_project_id, project_name)

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
                if status == "scraped" or status == "completed":
                    updates["error_message"] = ""
                    updates["failure_type"] = ""
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


async def _check_project_completion(project_id: str, project_name: str):
    """Check if all products in a project are in terminal states and send notification if so."""
    if not project_id:
        return
    try:
        async with async_session() as session:
            from sqlalchemy import func as sa_func
            total_result = await session.execute(
                select(sa_func.count(ProductLink.id)).where(ProductLink.project_id == project_id)
            )
            total = total_result.scalar() or 0
            if total == 0:
                return

            terminal_result = await session.execute(
                select(sa_func.count(ProductLink.id)).where(
                    ProductLink.project_id == project_id,
                    ProductLink.status.in_(["scraped", "completed", "failed", "error", "skipped"])
                )
            )
            terminal = terminal_result.scalar() or 0

            if terminal < total:
                halfway = terminal >= total / 2
                if halfway:
                    await send_notification(
                        user_id="",
                        title="Project Scraping Progress",
                        message=f"Project '{project_name}' is {terminal}/{total} products scraped ({int(terminal/total*100)}%)",
                        event_type="scraping_progress",
                        level=NotificationLevel.INFO,
                        project_id=project_id,
                        data={
                            "project_id": project_id,
                            "project_name": project_name,
                            "total": total,
                            "completed": terminal,
                            "progress_pct": int(terminal / total * 100),
                        },
                    )
                return

            scraped_result = await session.execute(
                select(sa_func.count(ProductLink.id)).where(
                    ProductLink.project_id == project_id,
                    ProductLink.status.in_(["scraped", "completed"])
                )
            )
            scraped_count = scraped_result.scalar() or 0
            failed_result = await session.execute(
                select(sa_func.count(ProductLink.id)).where(
                    ProductLink.project_id == project_id,
                    ProductLink.status.in_(["failed", "error"])
                )
            )
            failed_count = failed_result.scalar() or 0

            await send_notification(
                user_id="",
                title="Project Scraping Complete",
                message=f"Project '{project_name}' finished scraping — {scraped_count} succeeded, {failed_count} failed",
                event_type="project_completed",
                level=NotificationLevel.SUCCESS if failed_count == 0 else NotificationLevel.WARNING,
                project_id=project_id,
                data={
                    "project_id": project_id,
                    "project_name": project_name,
                    "total": total,
                    "succeeded": scraped_count,
                    "failed": failed_count,
                },
            )
    except Exception as e:
        logger.warning("project_completion_check_failed", project_id=project_id, error=str(e))


RECOVERY_MAX_ATTEMPTS = 3


async def recover_stuck_products(max_age_minutes: int = 30):
    """Find products stuck in 'scraping' or 'pending' past threshold and recover them."""
    recovered = 1
    total_recovered = 0
    project_ids: set[str] = set()

    try:
        async with async_session() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

            # Stuck in "scraping" — worker likely crashed mid-task
            for status_filter in ("scraping", "pending"):
                result = await session.execute(
                    select(ProductLink).where(
                        ProductLink.status == status_filter,
                        ProductLink.updated_at < cutoff,
                    )
                )
                for link in list(result.scalars().all()):
                    try:
                        meta = dict(link.meta or {})
                        attempts = meta.get("scrape_attempts", 0)
                        if attempts >= RECOVERY_MAX_ATTEMPTS:
                            link.status = "error"
                            link.error_message = f"Auto-recovered: failed after {attempts} scrape attempts"
                            link.failure_type = "max_attempts_exceeded"
                        else:
                            link.status = "error"
                            link.error_message = f"Auto-recovered: stuck in '{status_filter}' since {link.updated_at.isoformat()}"
                            link.failure_type = "timeout"
                        link.updated_at = datetime.utcnow()
                        link.completed_at = datetime.utcnow()
                        if link.project_id:
                            project_ids.add(link.project_id)
                        session.add(link)
                        total_recovered += 1
                    except Exception as e:
                        logger.warning("stuck_recovery_failed", product_id=link.id, status=link.status, error=str(e))

            if total_recovered > 0:
                await session.commit()

            # Check project completion for recovered products
            for pid in project_ids:
                try:
                    total_q = await session.execute(
                        select(func.count(ProductLink.id)).where(ProductLink.project_id == pid)
                    )
                    total = total_q.scalar() or 0
                    terminal_q = await session.execute(
                        select(func.count(ProductLink.id)).where(
                            ProductLink.project_id == pid,
                            ProductLink.status.in_(["scraped", "completed", "failed", "error", "skipped"]),
                        )
                    )
                    terminal = terminal_q.scalar() or 0
                    if total > 0 and terminal >= total:
                        scraped_q = await session.execute(
                            select(func.count(ProductLink.id)).where(
                                ProductLink.project_id == pid,
                                ProductLink.status.in_(["scraped", "completed"]),
                            )
                        )
                        scraped = scraped_q.scalar() or 0
                        failed_q = await session.execute(
                            select(func.count(ProductLink.id)).where(
                                ProductLink.project_id == pid,
                                ProductLink.status.in_(["failed", "error"]),
                            )
                        )
                        failed = failed_q.scalar() or 0
                        logger.info("project_completed_via_recovery", project_id=pid, total=total, scraped=scraped, failed=failed)
                        from services.notifications import send_notification, NotificationLevel
                        from services.event_bus import publish, PipelineEvent, EventType
                        await send_notification(
                            user_id="",
                            title="Project Scraping Complete",
                            message=f"Project finished scraping — {scraped} succeeded, {failed} failed",
                            event_type="project_completed",
                            level=NotificationLevel.SUCCESS if failed == 0 else NotificationLevel.WARNING,
                            project_id=pid,
                            data={"project_id": pid, "total": total, "succeeded": scraped, "failed": failed},
                        )
                        await publish(PipelineEvent(
                            event_type=EventType.NOTIFICATION,
                            job_id="",
                            data={"type": "project_completed", "project_id": pid},
                        ))
                except Exception as e:
                    logger.warning("project_completion_after_recovery_failed", project_id=pid, error=str(e))

            if total_recovered > 0:
                logger.info("stuck_products_recovered", count=total_recovered)
            else:
                logger.info("no_stuck_products_found")
            return total_recovered
    except Exception as e:
        logger.error("stuck_recovery_error", error=str(e))
        return 0


@celery_app.task(bind=True, max_retries=0)
def recover_stuck(self):
    """Celery periodic task to auto-recover stuck products."""
    run_async(recover_stuck_products())


async def _get_product_link_meta(url: str) -> dict:
    try:
        async with async_session() as session:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            result = await session.execute(select(ProductLink.meta).where(ProductLink.url_hash == url_hash))
            row = result.one_or_none()
            return dict(row[0]) if row and row[0] else {}
    except Exception:
        return {}


async def _increment_scrape_attempt(url: str) -> int:
    try:
        async with async_session() as session:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            result = await session.execute(select(ProductLink).where(ProductLink.url_hash == url_hash))
            link = result.scalar_one_or_none()
            if not link:
                return 0
            meta = dict(link.meta or {})
            attempts = meta.get("scrape_attempts", 0) + 1
            meta["scrape_attempts"] = attempts
            await session.execute(
                sql_update(ProductLink).where(ProductLink.id == link.id).values(meta=meta)
            )
            await session.commit()
            return attempts
    except Exception:
        return 0


async def _get_product_link_project_id(url: str) -> str:
    try:
        async with async_session() as session:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            result = await session.execute(select(ProductLink.project_id).where(ProductLink.url_hash == url_hash))
            row = result.one_or_none()
            return row[0] if row else ""
    except Exception:
        return ""


async def _get_product_link_id(url: str) -> str:
    try:
        async with async_session() as session:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            result = await session.execute(select(ProductLink.id).where(ProductLink.url_hash == url_hash))
            row = result.one_or_none()
            return row[0] if row else ""
    except Exception:
        return ""


async def _mark_job_failed(job_id: str, error_message: str, failure_type: str = "unknown"):
    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        existing_meta = dict(job.meta or {}) if job else {}
        existing_meta["failure_type"] = failure_type
        await repo.update_status(job_id, JobStatus.FAILED, error_message=error_message, meta=existing_meta)
