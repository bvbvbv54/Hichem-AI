from __future__ import annotations

import io
import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from workers.celery_app import celery_app
from workers.async_runner import run_async
from configs.settings import settings
from configs.logging import get_logger
from database.session import async_session
from database.repository import JobRepository, AssetRepository
from models.enums import JobStatus
from services.storage.local import LocalStorage
from services.storage.r2 import get_r2_storage
from services.event_bus import publish, EventType, PipelineEvent

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=settings.celery_task_retry_max, default_retry_delay=settings.celery_task_retry_delay)
def process_generation(self, job_id: str):
    """Process a single image generation job."""
    logger.info("processing_job", job_id=job_id)
    try:
        run_async(_execute_generation(job_id))
    except Exception as exc:
        logger.error("job_failed", job_id=job_id, error=str(exc), traceback=traceback.format_exc())
        run_async(_update_job_error(job_id, str(exc)))
        try:
            raise self.retry(exc=exc)
        except Exception:
            run_async(_mark_job_failed(job_id, str(exc)))


async def _publish_job_event(job_id: str, status: str, progress: float = 0.0, extra: dict | None = None):
    try:
        await publish(PipelineEvent(
            event_type=EventType.JOB_STAGE_CHANGED,
            job_id=job_id,
            data={"status": status, "progress": progress, **(extra or {})},
        ))
    except Exception:
        pass


async def _execute_generation(job_id: str):
    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if not job:
            logger.error("job_not_found", job_id=job_id)
            return

        try:
            await repo.update_status(job_id, JobStatus.PROCESSING)
            await _publish_job_event(job_id, JobStatus.PROCESSING.value)

            parameters = job.parameters or {}
            final_prompt = job.prompt or ""

            await repo.update_status(job_id, JobStatus.GENERATING)
            await _publish_job_event(job_id, JobStatus.GENERATING.value, 50.0)

            from services.nano_banana.client import NanoBananaClient
            from services.nano_banana.models import GenerationRequest

            provider = NanoBananaClient()
            try:
                gen_request = GenerationRequest(
                    prompt=final_prompt or job.prompt,
                    negative_prompt=job.negative_prompt or "",
                    width=job.width or 1024,
                    height=job.height or 1024,
                    num_images=job.num_images or 1,
                    model=job.model_name or "",
                )
                results = await provider.generate(gen_request)
            finally:
                await provider.close()

            total_pixels = (job.width or 1024) * (job.height or 1024)
            image_provider = settings.image_provider or "replicate"
            llm_calls = [{
                "provider": image_provider,
                "model": job.model_name or "flux",
                "type": "image_generation",
                "estimated_cost": round(total_pixels * 0.00000002, 6),
            }]

            await repo.update_status(job_id, JobStatus.STORING)
            await _publish_job_event(job_id, JobStatus.STORING.value, 75.0)

            asset_repo = AssetRepository(session)
            from services.storage.local import LocalStorage
            storage = LocalStorage()
            r2 = get_r2_storage()

            for idx, result in enumerate(results):
                filename = f"{job_id}_{idx+1}.png"
                storage_result = await storage.store(
                    data=result.image_data,
                    job_id=job_id,
                    filename=filename,
                    project_name=job.project_name or "",
                )

                asset_meta = dict(result.meta or {})
                r2_url = ""
                try:
                    r2_result = await r2.upload_file(
                        local_path=storage_result.file_path,
                        project_id=job.project_name or "default",
                        product_id=job_id,
                        category="ai-generated",
                        filename=filename,
                        content_type=storage_result.mime_type,
                    )
                    r2_url = r2_result["url"]
                    asset_meta["r2_url"] = r2_result["url"]
                    asset_meta["r2_key"] = r2_result["key"]
                except Exception as r2_err:
                    logger.warning("r2_gen_upload_failed", job_id=job_id, error=str(r2_err))

                asset_data = {
                    "job_id": job_id,
                    "filename": filename,
                    "original_filename": filename,
                    "file_path": storage_result.file_path,
                    "file_size": storage_result.file_size,
                    "mime_type": storage_result.mime_type,
                    "width": storage_result.width,
                    "height": storage_result.height,
                    "meta": asset_meta,
                }
                await asset_repo.create(asset_data)

            await repo.update_status(job_id, JobStatus.DELIVERING)
            await _publish_job_event(job_id, JobStatus.DELIVERING.value, 90.0)

            from services.delivery.local import create_delivery_backends
            delivery_backends = create_delivery_backends()
            assets = await asset_repo.list_by_job(job_id)

            for asset in assets:
                asset_data = await storage.retrieve(asset.file_path)
                if asset_data:
                    for backend in delivery_backends:
                        try:
                            await backend.deliver(
                                data=asset_data,
                                filename=asset.filename,
                                asset_id=asset.id,
                                job_id=job_id,
                                project_name=job.project_name or "",
                            )
                        except Exception as e:
                            logger.error("delivery_failed", asset_id=asset.id, error=str(e))

            current_meta = job.meta or {}
            existing_calls = current_meta.get("llm_calls", [])
            current_meta["llm_calls"] = existing_calls + llm_calls
            await repo.update(job_id, {"meta": current_meta})

            await repo.update_status(job_id, JobStatus.COMPLETED, progress=100.0)
            await _publish_job_event(job_id, JobStatus.COMPLETED.value, 100.0)
            logger.info("job_completed", job_id=job_id)

        except Exception as e:
            await repo.update_status(job_id, JobStatus.FAILED, error_message=str(e))
            await _publish_job_event(job_id, JobStatus.FAILED.value)
            raise


async def _update_job_error(job_id: str, error: str):
    async with async_session() as session:
        repo = JobRepository(session)
        await repo.update(job_id, {"status": "retrying", "error_message": error})
    await _publish_job_event(job_id, "retrying", extra={"error": error})


async def _mark_job_failed(job_id: str, error: str):
    async with async_session() as session:
        repo = JobRepository(session)
        await repo.update_status(job_id, JobStatus.FAILED, error_message=error)
    await _publish_job_event(job_id, JobStatus.FAILED.value, extra={"error": error})


@celery_app.task(bind=True, max_retries=3)
def process_bulk_generation(self, parent_job_id: str, batch_id: str, num_images: int, descriptions: list, prompt_template: str, model_name: str = ""):
    """Process bulk generation from uploaded products."""
    logger.info("process_bulk_generation_started", parent_job_id=parent_job_id, batch_id=batch_id, num_images=num_images, model_name=model_name)
    try:
        run_async(_execute_bulk_generation(parent_job_id, batch_id, num_images, descriptions, prompt_template, model_name))
    except Exception as exc:
        logger.error("bulk_generation_failed", error=str(exc), traceback=traceback.format_exc())
        run_async(_mark_job_failed(parent_job_id, str(exc)))


async def _execute_bulk_generation(parent_job_id: str, batch_id: str, num_images: int, descriptions: list, prompt_template: str, model_name: str = ""):
    async with async_session() as session:
        repo = JobRepository(session)
        parent = await repo.get(parent_job_id)
        if not parent:
            logger.error("parent_job_not_found", job_id=parent_job_id)
            return

        parent_meta = parent.meta or {}
        per_product_counts = parent_meta.get("per_product_counts", {})
        is_auto = num_images == -1

        # task-level model_name takes precedence over parent meta
        if not model_name:
            model_name = parent_meta.get("model_name", "")

        await repo.update_status(parent_job_id, JobStatus.PROCESSING)
        await _publish_job_event(parent_job_id, JobStatus.PROCESSING.value, 0.0, {"batch_id": batch_id})

        batch_dir = Path(settings.storage_path) / "uploads" / batch_id
        products_file = batch_dir / "products.json"
        if not products_file.exists():
            await repo.update_status(parent_job_id, JobStatus.FAILED, error_message="Products data not found")
            await _publish_job_event(parent_job_id, JobStatus.FAILED.value, extra={"error": "Products data not found"})
            return

        products = json.loads(products_file.read_text())
        total = len(products)

        await repo.update(parent_job_id, {"meta": {**parent_meta, "total": total}})

        storage = LocalStorage()
        r2 = get_r2_storage()
        from services.nano_banana.client import NanoBananaClient
        image_provider = NanoBananaClient()

        import hashlib
        from sqlalchemy import select
        from database.models.product_link import ProductLink
        from database.models.asset import Asset

        completed = 0
        failed = 0

        for pidx, product in enumerate(products):
            url = product["url"]

            # Load approved reference image paths from ProductLink assets
            ref_paths: list[str] = []
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            pl_result = await session.execute(
                select(ProductLink).where(ProductLink.url_hash == url_hash)
            )
            pl = pl_result.scalar_one_or_none()
            if pl:
                pl_meta = pl.meta or {}
                ref_ids = pl_meta.get("reference_selected_ids", [])
                if ref_ids:
                    asset_result = await session.execute(
                        select(Asset).where(Asset.id.in_(ref_ids))
                    )
                    for asset in asset_result.scalars().all():
                        fp = asset.file_path
                        if Path(fp).exists():
                            ref_paths.append(fp)

            images_for_product = per_product_counts.get(url, num_images) if is_auto else num_images
            images_for_product = max(1, min(images_for_product, 10))

            child_job = await repo.create({
                "type": "single",
                "status": "pending",
                "prompt": url,
                "project_name": parent.project_name or "default",
                "parent_job_id": parent_job_id,
                "is_bulk_item": True,
                "meta": {"url": url, "batch_id": batch_id, "reference_paths": ref_paths},
            })

            child_llm_calls: list[dict] = []

            try:
                results = await image_provider.generate_from_references(
                    reference_paths=ref_paths,
                    num_images=images_for_product,
                    model_name=model_name,
                    prompt="",
                    session=session,
                )
                child_llm_calls.append({
                    "provider": "replicate",
                    "model": model_name or "google/imagen-4",
                    "type": "image_generation",
                    "estimated_cost": 0.008,
                })

                if results:
                    asset_repo = AssetRepository(session)
                    for img_idx, img_data in enumerate(results):
                        filename = f"{child_job.id}_{img_idx+1}.png"
                        storage_result = await storage.store(
                            data=img_data.image_data,
                            job_id=child_job.id,
                            filename=filename,
                            project_name=parent.project_name or "",
                        )
                        asset_meta = {
                            "reference_paths": ref_paths,
                            "model": model_name or "",
                            "provider": "replicate",
                        }
                        try:
                            r2_result = await r2.upload_file(
                                local_path=storage_result.file_path,
                                project_id=parent.project_name or "default",
                                product_id=url.split("/")[-1][:36],
                                category="ai-generated",
                                filename=filename,
                                content_type=storage_result.mime_type,
                            )
                            asset_meta["r2_url"] = r2_result["url"]
                            asset_meta["r2_key"] = r2_result["key"]
                        except Exception as r2_err:
                            logger.warning("r2_bulk_gen_upload_failed", error=str(r2_err))
                        await asset_repo.create({
                            "job_id": child_job.id,
                            "filename": filename,
                            "original_filename": filename,
                            "file_path": storage_result.file_path,
                            "file_size": storage_result.file_size,
                            "mime_type": storage_result.mime_type,
                            "width": storage_result.width,
                            "height": storage_result.height,
                            "meta": asset_meta,
                        })
                    completed += images_for_product

            except Exception as e:
                logger.error("generation_failed", url=url, error=str(e))
                await repo.update_status(child_job.id, JobStatus.FAILED, error_message=str(e))
                failed += 1

            if child_llm_calls:
                child_meta = child_job.meta or {}
                child_meta["llm_calls"] = child_meta.get("llm_calls", []) + child_llm_calls
                await repo.update(child_job.id, {"meta": child_meta})

            progress = ((pidx + 1) / total) * 100
            await repo.update(parent_job_id, {"progress": progress})
            await _publish_job_event(parent_job_id, JobStatus.PROCESSING.value, progress, {"batch_id": batch_id, "completed": completed, "failed": failed, "total": total})

        final_status = JobStatus.COMPLETED if failed == 0 else JobStatus.PARTIALLY_COMPLETED if completed > 0 else JobStatus.FAILED
        await repo.update_status(parent_job_id, final_status, progress=100.0)
        await _publish_job_event(parent_job_id, final_status.value, 100.0, {"batch_id": batch_id, "completed": completed, "failed": failed, "total": total})
        logger.info("bulk_generation_complete", job_id=parent_job_id, completed=completed, failed=failed)


@celery_app.task(bind=True, max_retries=0)
def process_smoke_test(self, job_id: str, test_id: str):
    """Celery task to run the smoke test flow on the worker."""
    logger.info("processing_smoke_test_task", job_id=job_id, test_id=test_id)
    try:
        run_async(_execute_smoke_test(job_id, test_id))
    except Exception as exc:
        logger.error("smoke_test_task_failed", job_id=job_id, test_id=test_id, error=str(exc))
        run_async(_mark_job_failed(job_id, str(exc)))
        raise


async def _execute_smoke_test(job_id: str, test_id: str):
    from services.verification.cost_controller import CostController
    from services.verification.smoke_test import SmokeTestStep
    from services.nano_banana.client import NanoBananaClient
    from services.nano_banana.models import GenerationRequest
    from services.storage.local import LocalStorage
    from services.delivery.local import create_delivery_backends

    cost = CostController()
    steps = []

    async def run_step(name, coro):
        step_start = time.time()
        try:
            res = await coro()
            duration = (time.time() - step_start) * 1000
            steps.append({
                "name": name,
                "status": "passed",
                "duration_ms": duration,
                "details": res or {}
            })
            logger.info("smoke_task_step_passed", name=name, duration_ms=duration)
            await _publish_job_event(job_id, f"step_{name}_passed", progress=len(steps)*12.5)
            return res
        except Exception as e:
            duration = (time.time() - step_start) * 1000
            steps.append({
                "name": name,
                "status": "failed",
                "duration_ms": duration,
                "error": str(e)
            })
            logger.error("smoke_task_step_failed", name=name, error=str(e))
            await _publish_job_event(job_id, f"step_{name}_failed")
            raise

    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if not job:
            logger.error("smoke_job_not_found", job_id=job_id)
            return

        try:
            await repo.update_status(job_id, JobStatus.PROCESSING)
            await _publish_job_event(job_id, JobStatus.PROCESSING.value)

            # Step 1: Load sample product
            async def _load_product():
                return {
                    "title": "Smoke Test Apple",
                    "description": "A fresh red apple representing a smoke test product.",
                    "url": "https://example.com/smoke-test-apple"
                }
            product = await run_step("load_product", _load_product)

            # Step 2: Hardcoded prompt (no Claude)
            async def _text_gen():
                prompt = f"Professional product photograph of {product['title']}. Clean white background, studio lighting."
                return {"prompt": prompt, "response": prompt}
            text_result = await run_step("prompt_preparation", _text_gen)

            # Step 3: Image Generation
            async def _image_gen():
                cost.check_image_budget()
                provider = NanoBananaClient()
                try:
                    req = GenerationRequest(
                        prompt=text_result["response"],
                        num_images=1,
                        width=256,
                        height=256,
                        steps=1,
                        guidance_scale=1.0,
                    )
                    results = await provider.generate(req)
                    if not results:
                        raise RuntimeError("No images returned from provider")
                    cost.record_image_call(cost_cents=10)
                    return results[0]
                finally:
                    await provider.close()
            image_result = await run_step("image_generation", _image_gen)

            # Step 4: Storage
            async def _storage():
                storage = LocalStorage()
                filename = f"smoke_{test_id}.png"
                storage_result = await storage.store(
                    data=image_result.image_data,
                    job_id=job_id,
                    filename=filename,
                    project_name="__smoke_test__",
                )
                return {
                    "file_path": storage_result.file_path,
                    "file_size": storage_result.file_size,
                    "filename": filename
                }
            storage_res = await run_step("storage", _storage)

            # Step 5: Delivery
            async def _delivery():
                backends = create_delivery_backends()
                for backend in backends:
                    await backend.deliver(
                        data=image_result.image_data,
                        filename=storage_res["filename"],
                        asset_id=f"smoke-{test_id}",
                        job_id=job_id,
                        project_name="__smoke_test__",
                    )
                return {"delivered": len(backends)}
            await run_step("delivery", _delivery)

            # Update final job state
            await repo.update(job_id, {
                "status": JobStatus.COMPLETED.value,
                "progress": 100.0,
                "meta": {
                    "smoke_test_id": test_id,
                    "steps": steps,
                    "cost_cents": cost.total_cost_cents,
                    "text_calls_used": cost.text_calls_used,
                    "image_calls_used": cost.image_calls_used,
                }
            })
            await _publish_job_event(job_id, JobStatus.COMPLETED.value, 100.0, {
                "smoke_test_id": test_id,
                "steps": steps,
                "cost_cents": cost.total_cost_cents
            })

        except Exception as e:
            logger.error("smoke_test_failed", error=str(e))
            await repo.update(job_id, {
                "status": JobStatus.FAILED.value,
                "error_message": str(e),
                "meta": {
                    "smoke_test_id": test_id,
                    "steps": steps,
                    "cost_cents": cost.total_cost_cents
                }
            })
            await _publish_job_event(job_id, JobStatus.FAILED.value, extra={"error": str(e)})
            raise

