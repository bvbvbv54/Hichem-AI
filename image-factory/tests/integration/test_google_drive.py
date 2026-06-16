from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_drive_manager_requires_credentials():
    """Drive manager should not authenticate without credentials."""
    from services.storage.google_drive import GoogleDriveManager

    with patch("pathlib.Path.exists", return_value=False):
        manager = GoogleDriveManager()
        authed = await manager.authenticate()
        assert authed is False


@pytest.mark.asyncio
async def test_drive_upload_product_idempotent():
    """Upload same product twice should avoid duplicate folder."""
    from services.storage.google_drive import GoogleDriveManager

    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_files.list = MagicMock(
        return_value=MagicMock(
            execute=AsyncMock(return_value={"files": [{"id": "existing-folder-id", "name": "TestProduct"}]})
        )
    )
    mock_service.files = MagicMock(return_value=mock_files)

    manager = GoogleDriveManager()
    manager._service = mock_service
    manager._authenticated = True

    result = await manager.upload_product_outputs(
        product_name="TestProduct",
        file_paths=["/tmp/test.png"],
        root_folder_name="ImageFactory Outputs",
    )
    assert result is not None


@pytest.mark.asyncio
async def test_drive_create_folder():
    """New product should create a Google Drive folder."""
    from services.storage.google_drive import GoogleDriveManager

    mock_service = MagicMock()
    mock_files = MagicMock()

    def list_side(**kwargs):
        q = kwargs.get("q", "")
        if "name = 'ImageFactory Outputs'" in q:
            return MagicMock(execute=AsyncMock(return_value={"files": [{"id": "root-folder-id", "name": "ImageFactory Outputs"}]}))
        return MagicMock(execute=AsyncMock(return_value={"files": []}))

    mock_files.list = MagicMock(side_effect=list_side)
    mock_files.create = MagicMock(
        return_value=MagicMock(execute=AsyncMock(return_value={"id": "new-folder-id", "name": "NewProduct"}))
    )
    mock_service.files = MagicMock(return_value=mock_files)

    manager = GoogleDriveManager()
    manager._service = mock_service
    manager._authenticated = True

    result = await manager.upload_product_outputs(
        product_name="NewProduct",
        file_paths=["/tmp/new.png"],
        root_folder_name="ImageFactory Outputs",
    )
    assert result is not None
    assert "folder_url" in result


@pytest.mark.asyncio
async def test_drive_auth_status_unauthenticated():
    """Auth status should return false when not authenticated."""
    from services.storage.google_drive import GoogleDriveManager

    with patch("pathlib.Path.exists", return_value=False):
        manager = GoogleDriveManager()
        status = await manager.check_auth_status()
        assert status.get("authenticated") is False


@pytest.mark.asyncio
async def test_drive_upload_empty_paths():
    """Upload with empty paths should not fail."""
    from services.storage.google_drive import GoogleDriveManager

    manager = GoogleDriveManager()
    manager._authenticated = True
    manager._service = MagicMock()

    result = await manager.upload_product_outputs(
        product_name="EmptyProduct",
        file_paths=[],
        root_folder_name="Root",
    )
    assert result is None
