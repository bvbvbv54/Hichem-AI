from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_redis
from configs.settings import settings
from configs.logging import get_logger
from services.storage.google_drive import get_drive_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/google-drive", tags=["Google Drive"])


async def _ensure_auth():
    manager = get_drive_manager()
    if not manager.is_authenticated:
        authenticated = await manager.authenticate()
        if not authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated with Google Drive")
    return manager


@router.get("/auth/start")
async def auth_start(redis: aioredis.Redis = Depends(get_redis)):
    manager = get_drive_manager()
    state = str(uuid.uuid4())
    await redis.setex(f"gdrive:state:{state}", 600, "1")
    auth_url = manager.get_auth_url()
    return {"auth_url": auth_url, "state": state}


@router.get("/auth/callback")
async def auth_callback(
    code: str = Query(...),
    state: str = Query(...),
    redis: aioredis.Redis = Depends(get_redis),
):
    stored = await redis.get(f"gdrive:state:{state}")
    if not stored:
        raise HTTPException(status_code=403, detail="Invalid or expired state token")
    await redis.delete(f"gdrive:state:{state}")
    manager = get_drive_manager()
    result = await manager.handle_callback(code)
    return result


@router.get("/auth/status")
async def auth_status():
    manager = get_drive_manager()
    authenticated = await manager.authenticate()
    email = ""
    if authenticated and manager._creds:
        try:
            about = await asyncio.to_thread(manager._service.about().get(fields="user").execute)
            email = about.get("user", {}).get("emailAddress", "")
        except Exception:
            pass
    return {"authenticated": authenticated, "email": email}


@router.post("/upload")
async def upload_job_assets(
    job_id: str = Query(...),
    product_name: str = Query(...),
):
    manager = await _ensure_auth()
    output_dir = Path(settings.storage_path) / product_name / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"No output directory found for job {job_id}")
    file_paths = [str(f) for f in output_dir.iterdir() if f.is_file() and f.suffix in (".png", ".jpg", ".jpeg", ".webp")]
    if not file_paths:
        raise HTTPException(status_code=404, detail="No image files found in job output directory")
    result = await manager.upload_product_outputs(
        product_name=product_name,
        file_paths=file_paths,
        root_folder_name=settings.google_drive_root_folder,
    )
    return {"success": True, "folder_url": result["folder_url"], "files": result["files"], "folder_id": result["folder_id"]}


@router.get("/list")
async def list_folder(folder_id: str = Query(...)):
    manager = await _ensure_auth()
    files = await manager.list_folder_contents(folder_id)
    return {"files": files, "total": len(files)}


@router.post("/sync")
async def sync_unsynced_jobs(redis: aioredis.Redis = Depends(get_redis)):
    from database.session import async_session
    from database.repository import JobRepository
    from models.enums import JobStatus

    manager = await _ensure_auth()
    task_id = str(uuid.uuid4())
    unsynced: list[dict] = []
    async with async_session() as session:
        repo = JobRepository(session)
        completed = await repo.list_by_status(JobStatus.COMPLETED)
        for job in completed:
            meta = (job.metadata or {}) if hasattr(job, "metadata") else {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            if not meta.get("drive_folder_url"):
                unsynced.append({"job_id": job.id, "project_name": job.project_name or "", "product_name": meta.get("product_name", "")})
    synced_count = 0
    for item in unsynced:
        try:
            pname = item["product_name"] or item["project_name"]
            if not pname:
                continue
            output_dir = Path(settings.storage_path) / item["project_name"] / item["job_id"]
            if not output_dir.exists():
                continue
            file_paths = [str(f) for f in output_dir.iterdir() if f.is_file() and f.suffix in (".png", ".jpg", ".jpeg", ".webp")]
            if not file_paths:
                continue
            result = await manager.upload_product_outputs(
                product_name=pname, file_paths=file_paths, root_folder_name=settings.google_drive_root_folder,
            )
            async with async_session() as session:
                repo2 = JobRepository(session)
                meta_copy = {"drive_folder_url": result["folder_url"]}
                if isinstance(meta, dict):
                    meta_copy.update(meta)
                await repo2.update(item["job_id"], {"metadata": meta_copy})
            synced_count += 1
        except Exception as e:
            logger.warning("sync_failed_for_job", job_id=item["job_id"], error=str(e))
    return {"task_id": task_id, "synced": synced_count, "total_found": len(unsynced)}
