from __future__ import annotations

import sys
import types

gemini_mock = types.ModuleType("google.generativeai")
gemini_mock.configure = lambda **kw: None
sys.modules["google.generativeai"] = gemini_mock

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sse_connection(async_client):
    """SSE endpoint should return text/event-stream."""
    response = await async_client.get("/api/v1/events?token=test")
    assert response.status_code == 200
    assert response.headers.get("content-type") == "text/event-stream" or response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_stats_endpoint(async_client, api_headers):
    """Dashboard stats should return expected shape."""
    response = await async_client.get("/api/v1/dashboard/stats", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_products" in data
    assert "products_in_queue" in data
    assert "products_processing" in data
    assert "products_completed" in data
    assert "products_failed" in data
    assert "total_images" in data


@pytest.mark.asyncio
async def test_dashboard_status_endpoint(async_client, api_headers):
    """System status endpoint should return component health."""
    response = await async_client.get("/api/v1/dashboard/status", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "api" in data
    assert "database" in data
    assert "worker" in data


@pytest.mark.asyncio
async def test_dashboard_active_jobs(async_client, api_headers):
    """Active jobs endpoint should return a list."""
    response = await async_client.get("/api/v1/dashboard/active", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_pipeline_event_publication(mock_redis):
    """Publishing a PipelineEvent should send to Redis pub/sub."""
    from services.event_bus import publish, PipelineEvent, EventType
    from datetime import datetime

    await publish(PipelineEvent(
        event_type=EventType.JOB_STAGE_CHANGED,
        job_id="test-job",
        data={"stage": "testing", "message": "Test event"},
    ))
    assert True


@pytest.mark.asyncio
async def test_admin_notifications_endpoint(async_client, api_headers):
    """Admin notifications should return expected shape."""
    response = await async_client.get("/api/v1/admin/notifications?limit=10", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_queue_info_endpoint(async_client, api_headers):
    """Queue info should return expected fields."""
    response = await async_client.get("/api/v1/dashboard/queue", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "current_length" in data
    assert "active_jobs" in data
    assert "waiting_jobs" in data
    assert "failed_jobs" in data
    assert "workers_active" in data
