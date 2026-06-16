from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.user import Project
from database.models.asset import Asset
from database.models.job import Job
from configs.logging import get_logger

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

    return {"projects": [{"id": p.id, "name": p.name, "description": p.description or "", "status": p.status, "product_count": int(p.product_count or 0), "generated_image_count": int(p.generated_image_count or 0), "created_at": p.created_at.isoformat() if p.created_at else "", "updated_at": p.updated_at.isoformat() if p.updated_at else ""} for p in projects], "total": total}


@router.get("/{project_id}")
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Count products (jobs) and images (assets) for this project
    jobs_result = await session.execute(select(func.count(Job.id)).where(Job.project_name == p.name))
    product_count = jobs_result.scalar() or 0

    assets_result = await session.execute(select(func.count(Asset.id)).where(Asset.job_id.in_(select(Job.id).where(Job.project_name == p.name))))
    image_count = assets_result.scalar() or 0

    return {"id": p.id, "name": p.name, "description": p.description or "", "status": p.status, "product_count": product_count, "generated_image_count": image_count, "created_at": p.created_at.isoformat() if p.created_at else "", "updated_at": p.updated_at.isoformat() if p.updated_at else ""}


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

    query = select(Job).where(Job.project_name == p.name)
    if status:
        query = query.where(Job.status == status)
    query = query.order_by(desc(Job.created_at)).limit(limit).offset(offset)

    result = await session.execute(query)
    jobs = result.scalars().all()

    products = []
    for job in jobs:
        assets_result = await session.execute(select(Asset).where(Asset.job_id == job.id))
        assets = assets_result.scalars().all()
        products.append({
            "id": job.id,
            "url": job.prompt or "",
            "status": job.status,
            "generated_title": job.enhanced_prompt or "",
            "generated_description": "",
            "images": [{"id": a.id, "filename": a.filename, "file_path": a.file_path, "created_at": a.created_at.isoformat() if a.created_at else ""} for a in assets],
            "created_at": job.created_at.isoformat() if job.created_at else "",
        })

    return {"products": products, "total": len(products)}
