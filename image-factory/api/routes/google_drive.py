from __future__ import annotations

import json
import uuid
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_redis
from configs.settings import settings
from configs.logging import get_logger
from services.storage.google_drive import get_drive_manager
from pydantic import BaseModel

logger = get_logger(__name__)

router = APIRouter(prefix="/google-drive", tags=["Google Drive"])


async def _ensure_auth():
    sa_path = SERVICE_ACCOUNT_PATH
    if not sa_path.exists():
        raise HTTPException(status_code=401, detail="No Google Drive credentials configured. Add a service account in Settings.")
    try:
        from google.oauth2 import service_account
        manager = get_drive_manager()
        manager._service = None
        creds = service_account.Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        manager._creds = creds
        return manager
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid service account credentials: {e}")


SERVICE_ACCOUNT_DIR = Path(settings.google_drive_credentials_path).parent
SERVICE_ACCOUNT_PATH = SERVICE_ACCOUNT_DIR / "service_account.json"


class ServiceAccountInput(BaseModel):
    credentials_json: str


@router.post("/credentials")
async def save_credentials(data: ServiceAccountInput):
    """Save Google Service Account credentials (JSON from Google Cloud Console)."""
    try:
        parsed = json.loads(data.credentials_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    if "client_email" not in parsed or "private_key" not in parsed:
        raise HTTPException(status_code=400, detail="Missing required fields: client_email, private_key")
    SERVICE_ACCOUNT_DIR.mkdir(parents=True, exist_ok=True)
    SERVICE_ACCOUNT_PATH.write_text(data.credentials_json)
    return {"status": "saved", "client_email": parsed["client_email"]}


@router.get("/credentials")
async def get_credentials_status():
    if SERVICE_ACCOUNT_PATH.exists():
        try:
            data = json.loads(SERVICE_ACCOUNT_PATH.read_text())
            return {"configured": True, "client_email": data.get("client_email", "")}
        except Exception:
            pass
    return {"configured": False, "client_email": ""}


@router.post("/test")
async def test_drive_connection():
    """Test the Google Drive connection using saved service account."""
    if not SERVICE_ACCOUNT_PATH.exists():
        raise HTTPException(status_code=400, detail="No service account credentials saved")
    try:
        from google.oauth2 import service_account
        import googleapiclient.discovery
        creds = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_PATH),
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = googleapiclient.discovery.build("drive", "v3", credentials=creds)
        about = service.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        return {"status": "connected", "email": email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {e}")


@router.get("/auth/status")
async def auth_status():
    configured = SERVICE_ACCOUNT_PATH.exists()
    email = ""
    if configured:
        try:
            data = json.loads(SERVICE_ACCOUNT_PATH.read_text())
            email = data.get("client_email", "")
        except Exception:
            pass
    return {
        "authenticated": configured,
        "email": email,
        "root_folder": settings.google_drive_root_folder,
        "auto_upload": settings.google_drive_auto_upload,
    }


@router.post("/auth/disconnect")
async def auth_disconnect():
    if SERVICE_ACCOUNT_PATH.exists():
        SERVICE_ACCOUNT_PATH.unlink()
        logger.info("service_account_removed")
    return {"status": "disconnected"}


@router.get("/config")
async def get_drive_config():
    return {
        "root_folder": settings.google_drive_root_folder,
        "auto_upload": settings.google_drive_auto_upload,
        "token_path": settings.google_drive_token_path,
        "credentials_path": settings.google_drive_credentials_path,
    }


@router.put("/config")
async def update_drive_config(
    root_folder: str | None = None,
    auto_upload: bool | None = None,
):
    if root_folder is not None:
        settings.google_drive_root_folder = root_folder
    if auto_upload is not None:
        settings.google_drive_auto_upload = auto_upload
    return {"status": "updated", "root_folder": settings.google_drive_root_folder, "auto_upload": settings.google_drive_auto_upload}


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
