from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.user import Project
from database.models.asset import Asset
from database.models.job import Job
from database.models.product_link import ProductLink
from configs.logging import get_logger
from services.translation_service import batch_translate, contains_chinese

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_projects(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = select(Project)
    if status:
        query = query.where(Project.status == status)
    query = query.order_by(desc(Project.created_at)).limit(limit).offset(offset)

    result = await session.execute(query)
    projects = result.scalars().all()

    count_result = await session.execute(select(func.count(Project.id)))
    total = count_result.scalar() or 0

    result_list = []
    for p in projects:
        product_count_result = await session.execute(
            select(func.count(ProductLink.id)).where(ProductLink.project_id == p.id)
        )
        product_count = product_count_result.scalar() or 0
        assets_result = await session.execute(select(func.count(Asset.id)).where(Asset.job_id.in_(select(Job.id).where(Job.project_name == p.name))))
        ai_image_count = assets_result.scalar() or 0
        scraped_count_result = await session.execute(
            select(func.coalesce(func.sum(ProductLink.scraped_image_count), 0)).where(ProductLink.project_id == p.id)
        )
        scraped_image_count = scraped_count_result.scalar() or 0
        total_images = scraped_image_count + ai_image_count
        result_list.append({
            "id": p.id, "name": p.name, "description": p.description or "", "status": p.status,
            "product_count": product_count,
            "generated_image_count": total_images,
            "scraped_image_count": scraped_image_count,
            "created_at": p.created_at.isoformat() if p.created_at else "",
            "updated_at": p.updated_at.isoformat() if p.updated_at else "",
        })
    return {"projects": result_list, "total": total}


@router.get("/{project_id}")
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Count products and images for this project
    product_count_result = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.project_id == p.id)
    )
    product_count = product_count_result.scalar() or 0

    assets_result = await session.execute(select(func.count(Asset.id)).where(Asset.job_id.in_(select(Job.id).where(Job.project_name == p.name))))
    ai_image_count = assets_result.scalar() or 0
    scraped_count_result = await session.execute(
        select(func.coalesce(func.sum(ProductLink.scraped_image_count), 0)).where(ProductLink.project_id == p.id)
    )
    scraped_image_count = scraped_count_result.scalar() or 0
    total_images = scraped_image_count + ai_image_count

    return {"id": p.id, "name": p.name, "description": p.description or "", "status": p.status, "product_count": product_count, "generated_image_count": total_images, "scraped_image_count": scraped_image_count, "created_at": p.created_at.isoformat() if p.created_at else "", "updated_at": p.updated_at.isoformat() if p.updated_at else ""}


@router.post("")
async def create_project(req: CreateProjectRequest, session: AsyncSession = Depends(get_session)):
    project = Project(id=str(uuid.uuid4()), user_id="default", name=req.name, description=req.description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    logger.info("project_created", project_id=project.id)
    return {"id": project.id, "name": project.name, "description": project.description or "", "status": project.status, "product_count": 0, "generated_image_count": 0, "created_at": project.created_at.isoformat() if project.created_at else "", "updated_at": project.updated_at.isoformat() if project.updated_at else ""}


@router.delete("/{project_id}")
async def delete_project(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(Project).where(Project.id == project_id))
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted"}


@router.get("/{project_id}/jobs")
async def get_project_job_status(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    p_result = await session.execute(select(Project).where(Project.id == project_id))
    p = p_result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    p_links = await session.execute(
        select(ProductLink).where(ProductLink.project_id == project_id)
    )
    links = p_links.scalars().all()
    total = len(links)
    pending = sum(1 for l in links if l.status in ("pending", "queued"))
    scraping = sum(1 for l in links if l.status == "scraping")
    scraped = sum(1 for l in links if l.status == "scraped")
    completed = sum(1 for l in links if l.status == "completed")
    generating = sum(1 for l in links if l.status == "generating")
    failed = sum(1 for l in links if l.status in ("failed", "error"))
    skipped = sum(1 for l in links if l.status == "skipped")

    return {
        "total": total,
        "pending": pending,
        "scraping": scraping,
        "scraped": scraped,
        "completed": completed,
        "generating": generating,
        "failed": failed,
        "skipped": skipped,
    }


@router.get("/{project_id}/products")
async def get_project_products(
    project_id: str,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    p_result = await session.execute(select(Project).where(Project.id == project_id))
    p = p_result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Base query: ProductLink records for this project
    query = select(ProductLink).where(ProductLink.project_id == project_id)
    count_query = select(func.count(ProductLink.id)).where(ProductLink.project_id == project_id)
    if status:
        query = query.where(ProductLink.status == status)
        count_query = count_query.where(ProductLink.status == status)
    query = query.order_by(desc(ProductLink.updated_at)).limit(limit).offset(offset)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(query)
    links = result.scalars().all()

    products = []

    # Batch translate all Chinese product names in one call
    product_names = [link.product_name or "" for link in links]
    translated = await batch_translate(product_names) if any(contains_chinese(n) for n in product_names) else {}

    for link in links:
        images = []
        seen_paths: set[str] = set()
        if link.job_id:
            assets_result = await session.execute(select(Asset).where(Asset.job_id == link.job_id))
            assets = assets_result.scalars().all()
            for a in assets:
                fp = a.file_path or ""
                if fp and fp in seen_paths:
                    continue
                if fp:
                    seen_paths.add(fp)
                images.append({
                    "id": a.id,
                    "filename": a.filename,
                    "file_path": fp,
                    "created_at": a.created_at.isoformat() if a.created_at else "",
                })
            job_result = await session.execute(select(Job).where(Job.id == link.job_id))
            job = job_result.scalar_one_or_none()
            if job and job.meta:
                saved = job.meta.get("saved_assets", [])
                for img_path in saved:
                    if img_path in seen_paths:
                        continue
                    seen_paths.add(img_path)
                    img_id = hashlib.sha256(img_path.encode()).hexdigest()[:12]
                    images.append({
                        "id": img_id,
                        "filename": Path(img_path).name,
                        "file_path": img_path,
                        "created_at": job.completed_at.isoformat() if job.completed_at else "",
                    })

        name = link.product_name or ""
        title = translated.get(name, name)
        products.append({
            "id": link.id,
            "url": link.url or "",
            "status": link.status,
            "generated_title": title,
            "generated_description": "",
            "images": images,
            "scraped_image_count": link.scraped_image_count or 0,
            "generated_image_count": link.generated_image_count or 0,
            "created_at": link.created_at.isoformat() if link.created_at else "",
            "updated_at": link.updated_at.isoformat() if link.updated_at else "",
        })

    return {"products": products, "total": total}
