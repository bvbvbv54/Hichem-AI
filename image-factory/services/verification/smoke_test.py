from __future__ import annotations

import asyncio
import io
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from configs.settings import settings
from configs.logging import get_logger
from services.verification.cost_controller import CostController, BudgetExceededError
from services.verification.system_checks import SystemChecker

logger = get_logger(__name__)

SMOKE_SAMPLE_PROMPT = "A simple red apple on a white surface"


@dataclass
class SmokeTestStep:
    name: str
    status: str  # "pending" | "running" | "passed" | "failed" | "skipped"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmokeTestResult:
    id: str
    status: str  # "running" | "passed" | "failed" | "partial"
    started_at: str
    completed_at: Optional[str] = None
    steps: list[SmokeTestStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    text_calls_used: int = 0
    image_calls_used: int = 0
    estimated_cost_cents: int = 0
    error: str = ""
    summary: str = ""


class SmokeTestEngine:
    """Runs a single end-to-end smoke test with absolute minimum resource consumption."""

    def __init__(self) -> None:
        self.cost = CostController()
        self.checker = SystemChecker()
        self.test_id = str(uuid.uuid4())
        self.steps: list[SmokeTestStep] = []
        self.result: Optional[SmokeTestResult] = None

    async def run(self) -> SmokeTestResult:
        start_time = time.time()
        started_at = datetime.utcnow().isoformat()

        logger.info("smoke_test_started", test_id=self.test_id)

        # 1. Run local pre-flight checks
        local_checks = [
            ("system_checks", self._step_system_checks),
            ("database", self._step_database),
            ("redis", self._step_redis),
        ]

        passed_count = 0
        failed_count = 0

        for name, coro in local_checks:
            step = SmokeTestStep(name=name, status="running", started_at=time.time())
            self.steps.append(step)
            try:
                res = await coro()
                step.status = "passed"
                step.completed_at = time.time()
                step.duration_ms = (step.completed_at - step.started_at) * 1000
                step.details = res
                passed_count += 1
                logger.info("smoke_local_step_passed", step=name, duration_ms=step.duration_ms)
            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                step.completed_at = time.time()
                step.duration_ms = (step.completed_at - step.started_at) * 1000
                failed_count += 1
                logger.error("smoke_local_step_failed", step=name, error=str(e))
                # Stop if basic system check / DB / Redis is offline
                break

        # 2. If local checks passed, create a job and queue the Celery worker task
        if failed_count == 0:
            from database.session import async_session
            from database.repository import JobRepository
            from workers.celery_app import celery_app

            async with async_session() as session:
                repo = JobRepository(session)
                job = await repo.create({
                    "type": "smoke_test",
                    "status": "pending",
                    "project_name": "__smoke_test__",
                    "parameters": {"test_id": self.test_id},
                    "meta": {"test_id": self.test_id}
                })
                job_id = job.id

            logger.info("smoke_test_queued", job_id=job_id)
            celery_app.send_task("tasks.generation.process_smoke_test", args=[job_id, self.test_id])

            # 3. Poll for the job status
            poll_start = time.time()
            timeout = 30.0
            completed_job = None

            while time.time() - poll_start < timeout:
                async with async_session() as session:
                    repo = JobRepository(session)
                    current_job = await repo.get(job_id)
                    if current_job and current_job.status in ("completed", "failed"):
                        completed_job = current_job
                        break
                await asyncio.sleep(0.5)

            if completed_job:
                job_meta = completed_job.meta or {}
                worker_steps = job_meta.get("steps", [])
                for ws in worker_steps:
                    self.steps.append(SmokeTestStep(
                        name=ws.get("name"),
                        status=ws.get("status"),
                        duration_ms=ws.get("duration_ms", 0.0),
                        error=ws.get("error", ""),
                        details=ws.get("details", {})
                    ))
                    if ws.get("status") == "passed":
                        passed_count += 1
                    else:
                        failed_count += 1

                self.cost.text_calls_used = job_meta.get("text_calls_used", 0)
                self.cost.image_calls_used = job_meta.get("image_calls_used", 0)
                self.cost.total_cost_cents = job_meta.get("cost_cents", 0)

                if completed_job.status == "failed" and failed_count == 0:
                    failed_count += 1  # Generic fallback if worker failed but didn't report steps
            else:
                # Timed out
                timeout_step = SmokeTestStep(
                    name="worker_execution",
                    status="failed",
                    error="Worker task execution timed out (30s)",
                )
                self.steps.append(timeout_step)
                failed_count += 1

        total_duration = (time.time() - start_time) * 1000
        final_status = "passed" if failed_count == 0 else "failed"

        summary_parts = []
        if passed_count > 0:
            summary_parts.append(f"{passed_count} step(s) passed")
        if failed_count > 0:
            summary_parts.append(f"{failed_count} step(s) failed")

        self.result = SmokeTestResult(
            id=self.test_id,
            status=final_status,
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            steps=self.steps,
            total_duration_ms=total_duration,
            text_calls_used=self.cost.text_calls_used,
            image_calls_used=self.cost.image_calls_used,
            estimated_cost_cents=self.cost.total_cost_cents,
            summary=", ".join(summary_parts) if summary_parts else "All systems operational",
        )

        logger.info(
            "smoke_test_completed",
            test_id=self.test_id,
            status=final_status,
            duration_ms=total_duration,
            cost_cents=self.cost.total_cost_cents,
        )

        return self.result


    async def _step_system_checks(self) -> dict[str, Any]:
        self.cost.check_text_budget()
        results = await self.checker.run_all()
        failures = [r for r in results if r.status == "offline"]
        if failures:
            names = [f.component for f in failures]
            raise RuntimeError(f"System components offline: {', '.join(names)}")
        return {r.component: r.status for r in results}

    async def _step_database(self) -> dict[str, Any]:
        from database.session import engine
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1 AS ok")
            row = result.fetchone()
            if not row or row[0] != 1:
                raise RuntimeError("Database basic query failed")
        return {"query": "SELECT 1", "result": "ok"}

    async def _step_redis(self) -> dict[str, Any]:
        import redis.asyncio as redis_async
        r = redis_async.from_url(settings.redis_url, socket_connect_timeout=5)
        await r.set("smoke:ping", "pong", ex=60)
        val = await r.get("smoke:ping")
        await r.delete("smoke:ping")
        await r.aclose()
        if val != b"pong":
            raise RuntimeError("Redis set/get verification failed")
        return {"set_get": "ok"}

    async def _step_storage(self) -> dict[str, Any]:
        from services.storage.local import LocalStorage
        storage = LocalStorage()
        test_data = b"smoke-test-image-data"
        result = await storage.store(
            data=test_data,
            job_id=f"smoke-{self.test_id}",
            filename="smoke-test.txt",
            project_name="__smoke_test__",
        )
        retrieved = await storage.retrieve(result.file_path)
        await storage.delete(result.file_path)
        if retrieved != test_data:
            raise RuntimeError("Storage store/retrieve mismatch")
        return {"file_path": result.file_path, "file_size": result.file_size}

    async def _step_delivery(self) -> dict[str, Any]:
        from services.delivery.local import create_delivery_backends
        backends = create_delivery_backends()
        if not backends:
            raise RuntimeError("No delivery backends configured")
        delivery_results = []
        for backend in backends:
            healthy = await backend.check_health()
            delivery_results.append({backend.__class__.__name__: "healthy" if healthy else "unhealthy"})
        return {"backends": delivery_results}

    async def _step_text_generation(self) -> dict[str, Any]:
        return {"prompt": "Built-in prompt", "response": SMOKE_SAMPLE_PROMPT, "source": "hardcoded"}

    async def _step_image_generation(self) -> dict[str, Any]:
        self.cost.check_image_budget()
        from services.nano_banana.client import NanoBananaClient
        from services.nano_banana.models import GenerationRequest
        provider = NanoBananaClient()
        try:
            request = GenerationRequest(
                prompt=SMOKE_SAMPLE_PROMPT,
                num_images=1,
                width=256,
                height=256,
                steps=1,
                guidance_scale=1.0,
            )
            results = await provider.generate(request)
            if not results:
                raise RuntimeError("No images returned from provider")
            first = results[0]
            self.cost.record_image_call(cost_cents=10)
            return {
                "num_results": len(results),
                "width": first.width,
                "height": first.height,
                "size_bytes": len(first.image_data),
            }
        finally:
            await provider.close()

    async def _step_job_completion(self) -> dict[str, Any]:
        from database.session import async_session
        from database.repository import JobRepository
        async with async_session() as session:
            repo = JobRepository(session)
            job = await repo.create({
                "type": "smoke_test",
                "status": "completed",
                "prompt": SMOKE_SAMPLE_PROMPT,
                "project_name": "__smoke_test__",
                "metadata": {"smoke_test_id": self.test_id, "type": "smoke_test"},
            })
            fetched = await repo.get(job.id)
            if not fetched or fetched.status != "completed":
                raise RuntimeError("Job create/read verification failed")
            stats = await repo.get_stats()
        return {"job_id": job.id, "total_jobs_in_db": stats.get("total_jobs", 0)}
