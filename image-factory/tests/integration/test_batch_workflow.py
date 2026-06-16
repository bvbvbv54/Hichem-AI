from __future__ import annotations

import sys
import types

gemini_mock = types.ModuleType("google.generativeai")
gemini_mock.configure = lambda **kw: None
sys.modules["google.generativeai"] = gemini_mock

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_upload_parse_result(sample_xlsx, api_headers):
    """Upload sample_products.xlsx — assert parse_result fields."""
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    result = await reader.read_bytes(sample_xlsx, "test.xlsx")
    assert result.total_rows == 10
    assert result.valid_rows == 7
    assert result.skipped_rows == 2
    assert result.duplicate_rows == 1


@pytest.mark.asyncio
async def test_batch_created_with_child_jobs(sample_xlsx, async_client, api_headers):
    """POST /products/upload should create batch with correct child count."""
    with patch("api.routes.products.celery_app") as mock_celery:
        mock_celery.send_task = MagicMock()
        response = await async_client.post(
            "/api/v1/products/upload",
            files={"file": ("test.xlsx", sample_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["parse_result"]["valid_rows"] == 7
        assert data["parse_result"]["total_rows"] == 10
        assert data["parse_result"]["skipped_rows"] == 2
        assert data["parse_result"]["duplicate_rows"] == 1
        assert data["batch_id"] == data["job_id"]
        assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_batch_status_returns_progress(sample_xlsx, async_client, api_headers):
    """GET /products/batch/{id} should return progress with items."""
    with patch("api.routes.products.celery_app") as mock_celery:
        mock_celery.send_task = MagicMock()

        upload_resp = await async_client.post(
            "/api/v1/products/upload",
            files={"file": ("test.xlsx", sample_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=api_headers,
        )
        batch_id = upload_resp.json()["batch_id"]

        status_resp = await async_client.get(f"/api/v1/products/batch/{batch_id}", headers=api_headers)
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["batch_id"] == batch_id
        assert data["progress"]["total"] == 7
        assert len(data["items"]) == 7


@pytest.mark.asyncio
async def test_batch_pause_resume(sample_xlsx, async_client, api_headers):
    """Batch pause should stop dispatch, resume should re-enable."""
    with patch("api.routes.products.celery_app") as mock_celery:
        mock_celery.send_task = MagicMock()
        with patch("api.routes.products.get_redis") as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            upload_resp = await async_client.post(
                "/api/v1/products/upload",
                files={"file": ("test.xlsx", sample_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                headers=api_headers,
            )
            batch_id = upload_resp.json()["batch_id"]

            pause_resp = await async_client.post(f"/api/v1/products/batch/{batch_id}/pause", headers=api_headers)
            assert pause_resp.status_code == 200
            assert pause_resp.json()["status"] == "paused"

            resume_resp = await async_client.post(f"/api/v1/products/batch/{batch_id}/resume", headers=api_headers)
            assert resume_resp.status_code == 200
            assert resume_resp.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_batch_retry_failed(sample_xlsx, async_client, api_headers):
    """Retry-failed should requeue only failed jobs."""
    with patch("api.routes.products.celery_app") as mock_celery:
        mock_celery.send_task = MagicMock()
        with patch("api.routes.products.get_redis") as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            upload_resp = await async_client.post(
                "/api/v1/products/upload",
                files={"file": ("test.xlsx", sample_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                headers=api_headers,
            )
            batch_id = upload_resp.json()["batch_id"]

            retry_resp = await async_client.post(f"/api/v1/products/batch/{batch_id}/retry-failed", headers=api_headers)
            assert retry_resp.status_code == 200
            assert "retried_count" in retry_resp.json()


@pytest.mark.asyncio
async def test_batch_export_csv(sample_xlsx, async_client, api_headers):
    """Export should return valid CSV."""
    with patch("api.routes.products.celery_app") as mock_celery:
        mock_celery.send_task = MagicMock()
        upload_resp = await async_client.post(
            "/api/v1/products/upload",
            files={"file": ("test.xlsx", sample_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=api_headers,
        )
        batch_id = upload_resp.json()["batch_id"]

        export_resp = await async_client.get(f"/api/v1/products/batch/{batch_id}/export", headers=api_headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "text/csv"
        body = export_resp.text
        assert "URL" in body
        assert "Product Name" in body
        assert "Status" in body
        assert "Drive Folder URL" in body
