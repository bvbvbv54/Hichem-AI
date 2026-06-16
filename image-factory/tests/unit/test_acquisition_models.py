from __future__ import annotations

from datetime import datetime

import pytest


@pytest.mark.asyncio
async def test_acquisition_job_defaults():
    from services.acquisition.models import AcquisitionJob
    job = AcquisitionJob(job_id="test-123", url="https://example.com")
    assert job.job_id == "test-123"
    assert job.url == "https://example.com"
    assert job.max_images == 10
    assert job.priority == 0
    assert isinstance(job.created_at, datetime)
    assert job.attempts == 0
    assert job.last_error is None


@pytest.mark.asyncio
async def test_acquisition_job_custom():
    from services.acquisition.models import AcquisitionJob
    job = AcquisitionJob(job_id="abc", url="https://test.com", max_images=5, priority=3)
    assert job.max_images == 5
    assert job.priority == 3


@pytest.mark.asyncio
async def test_acquisition_result_success():
    from services.acquisition.models import AcquisitionResult
    r = AcquisitionResult(job_id="j1", url="https://example.com", success=True, image_paths=["/tmp/a.jpg", "/tmp/b.jpg"])
    assert r.success is True
    assert len(r.image_paths) == 2
    assert r.failure_type is None


@pytest.mark.asyncio
async def test_acquisition_result_failure():
    from services.acquisition.models import AcquisitionResult, FailureType
    r = AcquisitionResult(
        job_id="j1", url="https://example.com", success=False,
        failure_type=FailureType.BOT_BLOCKED, failure_detail="Blocked by Cloudflare",
    )
    assert r.success is False
    assert r.failure_type == FailureType.BOT_BLOCKED
    assert r.failure_detail == "Blocked by Cloudflare"


@pytest.mark.asyncio
async def test_failure_type_values():
    from services.acquisition.models import FailureType
    assert FailureType.NETWORK_ERROR.value == "network_error"
    assert FailureType.TIMEOUT.value == "timeout"
    assert FailureType.RATE_LIMITED.value == "rate_limited"
    assert FailureType.CAPTCHA.value == "captcha"
    assert FailureType.BOT_BLOCKED.value == "bot_blocked"
    assert FailureType.ROBOTS_DISALLOWED.value == "robots_disallowed"


@pytest.mark.asyncio
async def test_acquisition_result_cached_flag():
    from services.acquisition.models import AcquisitionResult
    r = AcquisitionResult(job_id="j1", url="https://example.com", success=True, was_cached=True)
    assert r.was_cached is True


@pytest.mark.asyncio
async def test_acquisition_result_browser_flag():
    from services.acquisition.models import AcquisitionResult
    r = AcquisitionResult(job_id="j1", url="https://example.com", success=True, required_browser=True)
    assert r.required_browser is True
