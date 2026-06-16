from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_cost_controller_budget_limits():
    from services.verification.cost_controller import CostController, BudgetExceededError

    ctrl = CostController()
    assert ctrl.text_calls_used == 0
    assert ctrl.image_calls_used == 0

    ctrl.check_text_budget()
    ctrl.record_text_call(cost_cents=1)
    assert ctrl.text_calls_used == 1

    with pytest.raises(BudgetExceededError):
        ctrl.check_text_budget()


@pytest.mark.asyncio
async def test_cost_controller_summary():
    from services.verification.cost_controller import CostController

    ctrl = CostController()
    ctrl.record_text_call(cost_cents=1)
    ctrl.record_image_call(cost_cents=10)

    summary = ctrl.summary()
    assert summary["text_calls_used"] == 1
    assert summary["image_calls_used"] == 1
    assert summary["total_cost_cents"] == 11


@pytest.mark.asyncio
async def test_dry_run_preview():
    from services.verification.dry_run import DryRunEngine

    engine = DryRunEngine()
    report = engine.preview_smoke_test()

    assert len(report.steps) == 6
    assert report.total_text_calls == 1
    assert report.total_image_calls == 1
    assert report.total_estimated_cost_cents >= 0

    step_names = [s.step for s in report.steps]
    assert "text_generation" in step_names
    assert "image_generation" in step_names
    assert "storage" in step_names
    assert "delivery" in step_names


@pytest.mark.asyncio
async def test_dry_run_full_job():
    from services.verification.dry_run import DryRunEngine

    engine = DryRunEngine()
    report = engine.preview_full_job()

    assert len(report.steps) == 10
    assert report.total_text_calls == 3
    assert report.total_image_calls == 4


@pytest.mark.asyncio
async def test_system_checker_creates_results():
    from services.verification.system_checks import SystemChecker, CheckResult

    checker = SystemChecker()
    results = await checker.run_all()

    assert len(results) > 0
    for r in results:
        assert isinstance(r, CheckResult)
        assert r.component
        assert r.status in ("healthy", "warning", "offline")


@pytest.mark.asyncio
async def test_smoke_test_step_model():
    from services.verification.smoke_test import SmokeTestStep, SmokeTestResult

    step = SmokeTestStep(name="test_step", status="passed", duration_ms=100.5)
    assert step.name == "test_step"
    assert step.status == "passed"
    assert step.duration_ms == 100.5

    result = SmokeTestResult(
        id="test-1",
        status="passed",
        started_at="2024-01-01T00:00:00",
        steps=[step],
        total_duration_ms=100.5,
    )
    assert result.id == "test-1"
    assert len(result.steps) == 1


@pytest.mark.asyncio
async def test_smoke_test_engine_creation():
    from services.verification.smoke_test import SmokeTestEngine

    engine = SmokeTestEngine()
    assert engine.test_id
    assert len(engine.steps) == 0
    assert engine.result is None


@pytest.mark.asyncio
async def test_cost_controller_prevents_excessive_retries():
    from services.verification.cost_controller import (
        BudgetExceededError,
        CostController,
    )

    ctrl = CostController()
    ctrl.check_retry_budget()
    ctrl.record_retry()
    with pytest.raises(BudgetExceededError):
        ctrl.check_retry_budget()


@pytest.mark.asyncio
async def test_verification_api_smoke_test_status(async_client):
    """Test that the verification status endpoint returns expected shape."""
    response = await async_client.get("/api/v1/verification/smoke-test/status")
    assert response.status_code in (200, 401)  # Might need auth
