from __future__ import annotations

import sys
import types

gemini_mock = types.ModuleType("google.generativeai")
gemini_mock.configure = lambda **kw: None
sys.modules["google.generativeai"] = gemini_mock

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_health_check(async_client):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_unauthorized_access(async_client):
    response = await async_client.get("/api/v1/jobs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_templates_list(async_client):
    response = await async_client.get(
        "/api/v1/templates",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data
    assert len(data["templates"]) >= 10


@pytest.mark.asyncio
async def test_templates_filter_by_category(async_client):
    response = await async_client.get(
        "/api/v1/templates?category=product_mockup",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(t["category"] == "product_mockup" for t in data["templates"])


@pytest.mark.asyncio
async def test_get_template_by_name(async_client):
    response = await async_client.get(
        "/api/v1/templates/product_mockup",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Product Mockup"


@pytest.mark.asyncio
async def test_generate_without_prompt_or_subject(async_client):
    response = await async_client.post(
        "/api/v1/generate",
        json={},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_with_prompt(async_client):
    with patch("tasks.generation.process_generation") as mock_task:
        mock_task.delay = MagicMock()
        response = await async_client.post(
            "/api/v1/generate",
            json={"prompt": "Test prompt"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_generate_with_subject(async_client):
    with patch("tasks.generation.process_generation") as mock_task:
        mock_task.delay = MagicMock()
        response = await async_client.post(
            "/api/v1/generate",
            json={"subject": "Red luxury handbag", "use_claude": True},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data


@pytest.mark.asyncio
async def test_bulk_generate(async_client):
    with patch("tasks.generation.process_bulk_generation") as mock_task:
        mock_task.delay = MagicMock()
        response = await async_client.post(
            "/api/v1/generate/bulk",
            json={
                "entries": [
                    {"prompt": "Image 1"},
                    {"prompt": "Image 2"},
                ],
                "project_name": "test-bulk",
            },
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 2


@pytest.mark.asyncio
async def test_get_nonexistent_job(async_client):
    response = await async_client.get(
        "/api/v1/jobs/nonexistent-id",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stats_endpoint(async_client):
    response = await async_client.get(
        "/api/v1/stats",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
