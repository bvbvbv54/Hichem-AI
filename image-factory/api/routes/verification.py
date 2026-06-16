from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.job import Job
from configs.settings import settings
from configs.logging import get_logger
from services.verification.smoke_test import SmokeTestEngine
from services.verification.system_checks import SystemChecker
from services.verification.dry_run import DryRunEngine

logger = get_logger(__name__)

router = APIRouter(prefix="/verification", tags=["Verification"])

_latest_result = None
_running_test = False


@router.post("/smoke-test", summary="Start a smoke test")
async def start_smoke_test():
    global _running_test, _latest_result

    if _running_test:
        raise HTTPException(status_code=409, detail="A smoke test is already running")

    _running_test = True
    engine = SmokeTestEngine()
    try:
        result = await engine.run()
        _latest_result = {
            "id": result.id,
            "status": result.status,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "total_duration_ms": round(result.total_duration_ms, 2),
            "text_calls_used": result.text_calls_used,
            "image_calls_used": result.image_calls_used,
            "estimated_cost_cents": result.estimated_cost_cents,
            "summary": result.summary,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "duration_ms": round(s.duration_ms, 2),
                    "error": s.error,
                    "details": s.details,
                }
                for s in result.steps
            ],
        }
        logger.info("smoke_test_complete", status=result.status, cost=result.estimated_cost_cents)
        return _latest_result
    except Exception as e:
        logger.error("smoke_test_failed", error=str(e))
        _latest_result = {"id": "error", "status": "failed", "error": str(e), "summary": "Smoke test crashed"}
        raise HTTPException(status_code=500, detail=f"Smoke test failed: {e}")
    finally:
        _running_test = False


@router.get("/smoke-test/status", summary="Get smoke test status")
async def get_smoke_test_status():
    if _running_test:
        return {"running": True, "message": "Smoke test in progress"}
    if _latest_result is None:
        return {"running": False, "tested": False, "message": "No smoke test has been run yet"}
    return {"running": False, "tested": True, "result": _latest_result}


@router.get("/smoke-test/latest", summary="Get latest smoke test result")
async def get_latest_smoke_test():
    if _latest_result is None:
        raise HTTPException(status_code=404, detail="No smoke test results available")
    return _latest_result


@router.post("/dry-run", summary="Preview pipeline without consuming credits")
async def dry_run():
    engine = DryRunEngine()
    report = engine.preview_smoke_test()
    return {
        "mode": "dry_run",
        "steps": [
            {"step": s.step, "action": s.action, "estimated_cost_cents": s.estimated_cost_cents, "estimated_duration_s": s.estimated_duration_s, "description": s.description}
            for s in report.steps
        ],
        "total_estimated_cost_cents": report.total_estimated_cost_cents,
        "total_estimated_duration_s": round(report.total_estimated_duration_s, 1),
        "total_text_calls": report.total_text_calls,
        "total_image_calls": report.total_image_calls,
        "warnings": report.warnings,
    }


@router.get("/health-checks", summary="Run full system health check")
async def run_health_checks():
    checker = SystemChecker()
    results = await checker.run_all()
    all_healthy = all(r.status == "healthy" for r in results)
    return {
        "all_healthy": all_healthy,
        "checks": [
            {
                "component": r.component,
                "status": r.status,
                "message": r.message,
                "latency_ms": round(r.latency_ms, 2),
            }
            for r in results
        ],
        "summary": "All systems healthy" if all_healthy else "Some checks failed",
    }


@router.get("/ready", summary="Final ready-for-flow verification")
async def ready_verification(session: AsyncSession = Depends(get_session)):
    """Returns a comprehensive readiness status for the entire platform."""
    checker = SystemChecker()
    checks = await checker.run_all()
    all_healthy = all(r.status == "healthy" for r in checks)

    job_count = await session.execute(select(func.count(Job.id)))
    total_jobs = job_count.scalar() or 0
    failed_count = await session.execute(select(func.count(Job.id)).where(Job.status == "failed"))
    total_failed = failed_count.scalar() or 0

    return {
        "ready": all_healthy and _latest_result is not None,
        "smoke_test_run": _latest_result is not None,
        "components": {r.component: r.status for r in checks},
        "database": {"total_jobs": total_jobs, "failed_jobs": total_failed},
        "latest_smoke_test": {
            "status": _latest_result.get("status") if _latest_result else None,
            "duration_ms": _latest_result.get("total_duration_ms") if _latest_result else None,
            "cost_cents": _latest_result.get("estimated_cost_cents") if _latest_result else None,
        } if _latest_result else None,
        "message": "System is ready for production flow" if all_healthy and _latest_result else "Run a smoke test to verify readiness",
    }
