from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.job import Job
from database.models.asset import Asset
from models.enums import JobStatus


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, job_data: dict[str, Any]) -> Job:
        job_id = job_data.pop("id", None) or str(uuid.uuid4())
        job = Job(id=job_id, **job_data)
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get(self, job_id: str) -> Optional[Job]:
        result = await self.session.execute(
            select(Job).options(selectinload(Job.assets)).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update(self, job_id: str, updates: dict[str, Any]) -> Optional[Job]:
        updates["updated_at"] = datetime.utcnow()
        await self.session.execute(update(Job).where(Job.id == job_id).values(**updates))
        await self.session.commit()
        return await self.get(job_id)

    async def update_status(self, job_id: str, status: JobStatus, **extra) -> Optional[Job]:
        updates = {"status": status.value, "updated_at": datetime.utcnow(), **extra}
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            updates["completed_at"] = datetime.utcnow()
        return await self.update(job_id, updates)

    async def list(
        self,
        status: Optional[JobStatus] = None,
        project: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        query = select(Job).options(selectinload(Job.assets))
        count_query = select(func.count(Job.id))

        if status:
            query = query.where(Job.status == status.value)
            count_query = count_query.where(Job.status == status.value)
        if project:
            query = query.where(Job.project_name == project)
            count_query = count_query.where(Job.project_name == project)

        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        query = query.order_by(desc(Job.created_at)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        jobs = list(result.scalars().all())

        return jobs, total

    async def list_by_parent(self, parent_job_id: str) -> list[Job]:
        result = await self.session.execute(
            select(Job).options(selectinload(Job.assets))
            .where(Job.parent_job_id == parent_job_id).order_by(Job.created_at)
        )
        return list(result.scalars().all())

    async def get_stats(self) -> dict[str, Any]:
        result = await self.session.execute(
            select(Job.status, func.count(Job.id)).group_by(Job.status)
        )
        status_counts = {row[0]: row[1] for row in result.all()}

        total = await self.session.execute(select(func.count(Job.id)))
        total_count = total.scalar() or 0

        return {
            "total_jobs": total_count,
            "status_counts": status_counts,
        }


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, asset_data: dict[str, Any]) -> Asset:
        asset = Asset(**asset_data)
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def get(self, asset_id: str) -> Optional[Asset]:
        result = await self.session.execute(select(Asset).where(Asset.id == asset_id))
        return result.scalar_one_or_none()

    async def list_by_job(self, job_id: str) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(Asset.job_id == job_id).order_by(Asset.created_at)
        )
        return list(result.scalars().all())

    async def update(self, asset_id: str, updates: dict[str, Any]) -> Optional[Asset]:
        await self.session.execute(update(Asset).where(Asset.id == asset_id).values(**updates))
        await self.session.commit()
        return await self.get(asset_id)

    async def delete(self, asset_id: str) -> bool:
        result = await self.session.execute(delete(Asset).where(Asset.id == asset_id))
        await self.session.commit()
        return result.rowcount > 0
