from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs.settings import settings
from configs.logging import get_logger
from database.session import get_session, async_session
from database.models.product_link import ProductLink
from database.models.job import Job
from database.models.asset import Asset
from database.repository import JobRepository
from services.storage.r2 import get_r2_storage
from services.notifications import send_notification, NotificationLevel
from services.utils import sanitize_filename
from starlette.responses import StreamingResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/export", tags=["Export"])


async def _collect_product_images(project_id: str) -> list[dict[str, Any]]:
    async with async_session() as session:
        products_result = await session.execute(
            select(ProductLink).where(ProductLink.project_id == project_id)
        )
        products = list(products_result.scalars().all())

        result: list[dict[str, Any]] = []
        for pl in products:
            product_name = pl.product_name or "unknown"
            scraped: list[dict[str, Any]] = []
            ai_generated: list[dict[str, Any]] = []

            meta = pl.meta or {}
            ref_ids = meta.get("reference_selected_ids", [])
            if ref_ids:
                assets_result = await session.execute(
                    select(Asset).where(Asset.id.in_(ref_ids))
                )
                for asset in assets_result.scalars().all():
                    ameta = asset.meta or {}
                    scraped.append({
                        "filename": asset.filename or "image.png",
                        "r2_url": ameta.get("r2_url", ""),
                        "r2_key": ameta.get("r2_key", ""),
                        "local_path": asset.file_path,
                    })

            jobs_result = await session.execute(
                select(Job).where(Job.meta["url"].as_string() == pl.url)
            )
            for job in jobs_result.scalars().all():
                assets_result = await session.execute(
                    select(Asset).where(Asset.job_id == job.id)
                )
                for asset in assets_result.scalars().all():
                    ameta = asset.meta or {}
                    is_scraped = ameta.get("type") == "scraped" or "scraped" in (asset.filename or "")
                    entry = {
                        "filename": asset.filename or "image.png",
                        "r2_url": ameta.get("r2_url", ""),
                        "r2_key": ameta.get("r2_key", ""),
                        "local_path": asset.file_path,
                    }
                    if is_scraped:
                        if not any(s["local_path"] == entry["local_path"] for s in scraped):
                            scraped.append(entry)
                    else:
                        ai_generated.append(entry)

            result.append({
                "product_name": product_name,
                "scraped": scraped,
                "ai_generated": ai_generated,
            })

        return result


async def _build_zip_stream(
    project_name: str,
    products_data: list[dict[str, Any]],
) -> bytes:
    buffer = io.BytesIO()
    safe_project = sanitize_filename(project_name)
    r2 = get_r2_storage()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for prod in products_data:
            safe_product = sanitize_filename(prod["product_name"])
            scraped_dir = f"{safe_project}/{safe_product}/scraped-images/"
            ai_dir = f"{safe_project}/{safe_product}/ai-generated/"

            for entry in prod["scraped"]:
                data = await _fetch_image_bytes(entry, r2)
                if data:
                    zf.writestr(f"{scraped_dir}{sanitize_filename(entry['filename'])}", data)

            if prod["ai_generated"]:
                for entry in prod["ai_generated"]:
                    data = await _fetch_image_bytes(entry, r2)
                    if data:
                        zf.writestr(f"{ai_dir}{sanitize_filename(entry['filename'])}", data)

    return buffer.getvalue()


async def _fetch_image_bytes(entry: dict[str, Any], r2: Any) -> bytes | None:
    r2_url = entry.get("r2_url", "")
    r2_key = entry.get("r2_key", "")
    local_path = entry.get("local_path", "")
    if r2_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(r2_url, timeout=30) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.warning("r2_fetch_failed", url=r2_url, error=str(e))
    # If stored URL failed (expired), try generating a fresh presigned URL if we have the key
    if r2_key:
        try:
            fresh_url = r2._public_url(r2_key)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(fresh_url, timeout=30) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.warning("r2_fresh_url_failed", key=r2_key, error=str(e))
    if local_path and Path(local_path).exists():
        try:
            return Path(local_path).read_bytes()
        except Exception as e:
            logger.warning("local_fetch_failed", path=local_path, error=str(e))
    return None


@router.get("/project/{project_id}/zip")
async def export_project_zip(
    project_id: str,
    project_name: str = Query("project", description="Display name for the ZIP root folder"),
    session: AsyncSession = Depends(get_session),
):
    products_data = await _collect_product_images(project_id)
    if not products_data:
        raise HTTPException(status_code=404, detail="No products found in project")

    zip_bytes = await _build_zip_stream(project_name, products_data)
    safe_name = sanitize_filename(project_name)

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


@router.post("/project/{project_id}/drive-export")
async def export_project_to_drive(
    project_id: str,
    project_name: str = Query("project", description="Display name for Drive folder"),
    session: AsyncSession = Depends(get_session),
):
    from services.storage.google_drive import get_drive_manager

    sa_dir = Path(settings.google_drive_credentials_path).parent
    sa_path = sa_dir / "service_account.json"
    if not sa_path.exists():
        raise HTTPException(status_code=400, detail="Google Drive not configured. Add a service account in Settings first.")

    manager = get_drive_manager()
    authed = await manager.use_service_account(str(sa_path))
    if not authed:
        raise HTTPException(status_code=401, detail="Google Drive authentication failed")

    products_data = await _collect_product_images(project_id)
    if not products_data:
        raise HTTPException(status_code=404, detail="No products found in project")

    # Create root folder
    safe_name = sanitize_filename(project_name)
    root_id = await manager.get_or_create_folder(safe_name)
    uploaded_count = 0
    errors: list[str] = []
    r2 = get_r2_storage()

    for prod in products_data:
        safe_product = sanitize_filename(prod["product_name"])
        product_folder_id = await manager.get_or_create_folder(safe_product, parent_id=root_id)

        scraped_folder_id = await manager.get_or_create_folder("scraped-images", parent_id=product_folder_id)
        for entry in prod["scraped"]:
            data = await _fetch_image_bytes(entry, r2)
            if not data:
                errors.append(f"Missing: {prod['product_name']}/{entry['filename']}")
                continue
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(entry["filename"]).suffix or ".jpg") as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name
                await manager.upload_file(
                    local_path=tmp_path,
                    drive_folder_id=scraped_folder_id,
                    filename=sanitize_filename(entry["filename"]),
                    make_public=settings.google_drive_make_public,
                )
                os.unlink(tmp_path)
                uploaded_count += 1
            except Exception as e:
                errors.append(f"Upload failed: {prod['product_name']}/{entry['filename']}: {e}")

        if prod["ai_generated"]:
            ai_folder_id = await manager.get_or_create_folder("ai-generated", parent_id=product_folder_id)
            for entry in prod["ai_generated"]:
                data = await _fetch_image_bytes(entry, r2)
                if not data:
                    continue
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(entry["filename"]).suffix or ".jpg") as tmp:
                        tmp.write(data)
                        tmp_path = tmp.name
                    await manager.upload_file(
                        local_path=tmp_path,
                        drive_folder_id=ai_folder_id,
                        filename=sanitize_filename(entry["filename"]),
                        make_public=settings.google_drive_make_public,
                    )
                    os.unlink(tmp_path)
                    uploaded_count += 1
                except Exception as e:
                    errors.append(f"AI upload failed: {prod['product_name']}/{entry['filename']}: {e}")

    # Notification
    if errors:
        await send_notification(
            user_id="",
            title="Drive Export: Partially Failed",
            message=f"Exported {uploaded_count} files to Drive ({len(errors)} errors)",
            event_type="delivery_completed",
            level=NotificationLevel.WARNING,
            data={"project_id": project_id, "project_name": project_name, "uploaded": uploaded_count, "errors": errors[:5]},
        )
        return {
            "status": "partial",
            "uploaded": uploaded_count,
            "errors": errors,
            "folder_url": f"https://drive.google.com/drive/folders/{root_id}",
        }

    folder_url = await manager.get_folder_url(root_id)
    await send_notification(
        user_id="",
        title="Drive Export Complete",
        message=f"{uploaded_count} files exported to Google Drive for '{project_name}'",
        event_type="delivery_completed",
        level=NotificationLevel.SUCCESS,
        data={"project_id": project_id, "project_name": project_name, "folder_url": folder_url, "uploaded": uploaded_count},
    )

    return {
        "status": "success",
        "uploaded": uploaded_count,
        "folder_url": folder_url,
    }
