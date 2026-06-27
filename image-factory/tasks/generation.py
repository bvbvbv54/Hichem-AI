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
            use_claude = parameters.get("use_claude", bool(settings.claude_api_key))
            enhance = parameters.get("enhance_prompt", True)
            subject = parameters.get("subject", "")

            final_prompt = job.prompt or ""

            llm_calls: list[dict] = []

            if use_claude and (not final_prompt or enhance):
                from services.claude.client import ClaudeClient
                claude = ClaudeClient()
                try:
                    if not final_prompt and subject:
                        style = parameters.get("style")
                        mood = parameters.get("mood")
                        context = parameters.get("context")
                        if job.template_name:
                            from services.claude.templates import get_template
                            from services.claude.enhancer import PromptEnhancer
                            template = get_template(job.template_name)
                            enhancer = PromptEnhancer(claude)
                            final_prompt = await enhancer.full_pipeline(
                                subject=subject,
                                template=template,
                                template_params=job.parameters.get("template_parameters"),
                                style=style,
                                mood=mood,
                                context=context,
                            )
                        else:
                            final_prompt = await claude.generate_prompt(
                                subject=subject, style=style, mood=mood, context=context,
                            )
                    elif enhance and final_prompt:
                        final_prompt = await claude.enhance_prompt(final_prompt)
                    usage = claude.last_usage
                    if usage:
                        llm_calls.append({
                            "provider": "anthropic",
                            "model": claude.model,
                            "input_tokens": usage.get("input_tokens", 0),
                            "output_tokens": usage.get("output_tokens", 0),
                        })
                finally:
                    await claude.close()

            await repo.update(job_id, {"enhanced_prompt": final_prompt, "status": JobStatus.ENHANCING_PROMPT.value})
            await _publish_job_event(job_id, JobStatus.ENHANCING_PROMPT.value, 25.0)

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
            llm_calls.append({
                "provider": image_provider,
                "model": job.model_name or "flux",
                "type": "image_generation",
                "estimated_cost": round(total_pixels * 0.00000002, 6),
            })

            await repo.update_status(job_id, JobStatus.STORING)
            await _publish_job_event(job_id, JobStatus.STORING.value, 75.0)

            asset_repo = AssetRepository(session)
            from services.storage.local import LocalStorage
            storage = LocalStorage()

            for idx, result in enumerate(results):
                filename = f"{job_id}_{idx+1}.png"
                storage_result = await storage.store(
                    data=result.image_data,
                    job_id=job_id,
                    filename=filename,
                    project_name=job.project_name or "",
                )

                asset_data = {
                    "job_id": job_id,
                    "filename": filename,
                    "original_filename": filename,
                    "file_path": storage_result.file_path,
                    "file_size": storage_result.file_size,
                    "mime_type": storage_result.mime_type,
                    "width": storage_result.width,
                    "height": storage_result.height,
                    "meta": result.meta,
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
def process_bulk_generation(self, parent_job_id: str, batch_id: str, num_images: int, descriptions: list, prompt_template: str):
    """Process bulk generation from uploaded products."""
    logger.info("process_bulk_generation_started", parent_job_id=parent_job_id, batch_id=batch_id, num_images=num_images)
    try:
        run_async(_execute_bulk_generation(parent_job_id, batch_id, num_images, descriptions, prompt_template))
    except Exception as exc:
        logger.error("bulk_generation_failed", error=str(exc), traceback=traceback.format_exc())
        run_async(_mark_job_failed(parent_job_id, str(exc)))


async def _execute_bulk_generation(parent_job_id: str, batch_id: str, num_images: int, descriptions: list, prompt_template: str):
    async with async_session() as session:
        repo = JobRepository(session)
        parent = await repo.get(parent_job_id)
        if not parent:
            logger.error("parent_job_not_found", job_id=parent_job_id)
            return

        parent_meta = parent.meta or {}
        per_product_counts = parent_meta.get("per_product_counts", {})
        is_auto = num_images == -1

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
        from services.nano_banana.client import NanoBananaClient
        from services.nano_banana.models import GenerationRequest
        image_provider = NanoBananaClient()

        completed = 0
        failed = 0

        for pidx, product in enumerate(products):
            url = product["url"]
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in url.split("/")[-1][:50])
            product_dir = batch_dir / safe_name

            scraped_files = list(product_dir.glob("*"))
            if not scraped_files:
                logger.warning("no_scraped_images", url=url)

            images_for_product = per_product_counts.get(url, num_images) if is_auto else num_images
            images_for_product = max(1, min(images_for_product, 10))

            product_title = product.get("title", "") or product.get("name", "") or url.split("/")[-1].replace("-", " ").replace("_", " ").title()

            child_job = await repo.create({
                "type": "single",
                "status": "pending",
                "prompt": url,
                "project_name": parent.project_name or "default",
                "parent_job_id": parent_job_id,
                "is_bulk_item": True,
                "meta": {"url": url, "batch_id": batch_id},
            })

            child_llm_calls: list[dict] = []

            for img_idx in range(images_for_product):
                if is_auto:
                    final_prompt = "Generate a professional product image based on this reference photo."
                else:
                    description = descriptions[img_idx] if img_idx < len(descriptions) else f"Product image {img_idx + 1}"

                    if prompt_template:
                        final_prompt = prompt_template.replace("{description}", description).replace("{url}", url)
                        for key, val in product.items():
                            final_prompt = final_prompt.replace("{" + key + "}", val)
                    else:
                        final_prompt = f"Professional e-commerce product photograph of {product_title or 'the product'}: {description}. Clean white background, studio lighting, 8K quality, commercial product photography."

                    text_instructions = (
                        "If the reference image contains any non-English text (e.g. Chinese, Arabic, etc.), "
                        "translate it into English and render the translated text neatly on the image. "
                        "Position all text with professional marketing layout — centered, well-spaced, "
                        "readable fonts, appropriate sizing."
                    )
                    final_prompt = f"{final_prompt}\n\n{text_instructions}"

                try:
                    gen_request = GenerationRequest(
                        prompt=final_prompt,
                        num_images=1,
                        width=1024,
                        height=1024,
                        model="google/imagen-4",
                        extra_params={"aspect_ratio": "1:1", "safety_filter_level": "block_medium_and_above"},
                    )
                    results = await image_provider.generate(gen_request)
                    child_llm_calls.append({
                        "provider": "replicate",
                        "model": "google/imagen-4",
                        "type": "image_generation",
                        "estimated_cost": 0.008,
                    })

                    if results:
                        asset_repo = AssetRepository(session)
                        for img_data in results:
                            filename = f"{child_job.id}_{img_idx+1}.png"
                            storage_result = await storage.store(
                                data=img_data.image_data,
                                job_id=child_job.id,
                                filename=filename,
                                project_name=parent.project_name or "",
                            )
                            await asset_repo.create({
                                "job_id": child_job.id,
                                "filename": filename,
                                "original_filename": filename,
                                "file_path": storage_result.file_path,
                                "file_size": storage_result.file_size,
                                "mime_type": storage_result.mime_type,
                                "width": storage_result.width,
                                "height": storage_result.height,
                                "meta": {"description": description, "prompt": final_prompt, "provider": "replicate"},
                            })

                except Exception as e:
                    logger.error("generation_failed", url=url, error=str(e))
                    await repo.update_status(child_job.id, JobStatus.FAILED, error_message=str(e))
                    failed += 1
                    continue

                completed += 1

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
    from services.claude.client import ClaudeClient
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

            # Step 2: Text Generation
            async def _text_gen():
                cost.check_text_budget()
                claude = ClaudeClient()
                if settings.smoke_use_cheapest_model:
                    claude.model = "claude-3-haiku-20240307"
                try:
                    prompt = f"Write a 1-sentence photo description for {product['title']}."
                    system = "You are a test assistant. Reply with a short description."
                    response = await claude.generate_text(
                        system_prompt=system,
                        user_prompt=prompt,
                        max_tokens=20,
                        temperature=0.0,
                    )
                    cost.record_text_call(cost_cents=1)
                    return {"prompt": prompt, "response": response.strip(), "model": claude.model}
                finally:
                    await claude.close()
            text_result = await run_step("text_generation", _text_gen)

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

