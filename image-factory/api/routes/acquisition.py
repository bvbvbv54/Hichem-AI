from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.product_link import ProductLink
from database.models.job import Job
from api.schemas.content import ProductLinkSchema
from configs.settings import settings
from configs.logging import get_logger
from services.acquisition.monitor import AcquisitionMonitor, _domain_from_url

logger = get_logger(__name__)

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])

SUPPORTED_SITES = {
    "amazon.com": "working",
    "amazon.co.uk": "working",
    "amazon.de": "working",
    "amazon.fr": "working",
    "amazon.it": "working",
    "amazon.es": "working",
    "amazon.ca": "working",
    "amazon.com.au": "working",
    "amazon.in": "working",
    "dhgate.com": "working",
    "made-in-china.com": "working",
    "1688.com": "working",
    "alibaba.com": "known_issues",
    "aliexpress.com": "known_issues",
    "jd.com": "not_supported",
    "taobao.com": "not_supported",
    "temu.com": "not_supported",
}

BANNED_DOMAINS = {"jd.com", "taobao.com", "temu.com"}

monitor = AcquisitionMonitor()


class SubmitUrlsRequest(BaseModel):
    urls: list[str]
    project_id: str = "default"


class SubmitUrlsResponse(BaseModel):
    accepted: int
    skipped_banned: int
    skipped_duplicates: int
    jobs: list[dict]


@router.post("/submit", summary="Submit product URLs for scraping")
async def submit_urls(
    req: SubmitUrlsRequest,
    session: AsyncSession = Depends(get_session),
):
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    now = datetime.utcnow()
    batch_id = str(uuid.uuid4())
    accepted = 0
    skipped_banned = 0
    skipped_duplicates = 0
    jobs = []

    for url in req.urls:
        url = url.strip()
        if not url:
            continue

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        if any(d in domain for d in BANNED_DOMAINS):
            skipped_banned += 1
            continue

        url_hash = hashlib.sha256(url.encode()).hexdigest()
        existing = await session.execute(
            select(ProductLink).where(ProductLink.url_hash == url_hash)
        )
        existing_link = existing.scalar_one_or_none()
        if existing_link and existing_link.status in ("completed", "generating", "scraping", "scraped"):
            skipped_duplicates += 1
            continue

        job_id = str(uuid.uuid4())
        meta = {
            "url": url,
            "product_name": "",
            "batch_index": len(jobs),
        }

        from database.repository import JobRepository
        repo = JobRepository(session)
        await repo.create({
            "id": job_id,
            "type": "single",
            "status": "queued",
            "project_name": req.project_id or "default",
            "parent_job_id": batch_id,
            "is_bulk_item": True,
            "progress": 0.0,
            "meta": meta,
        })

        link = ProductLink(
            url=url,
            url_hash=url_hash,
            project_id=req.project_id or "default",
            batch_id=batch_id,
            status="pending",
            job_id=job_id,
        )
        session.add(link)
        accepted += 1
        jobs.append({
            "url": url,
            "job_id": job_id,
            "domain": domain,
        })

    await session.commit()

    for job in jobs:
        from workers.celery_app import celery_app
        celery_app.send_task(
            "tasks.product.process_single_product",
            args=[job["job_id"], job["url"], req.project_id or "default"],
        )

    logger.info("urls_submitted", count=accepted, banned_skipped=skipped_banned, duplicates_skipped=skipped_duplicates)

    return SubmitUrlsResponse(
        accepted=accepted,
        skipped_banned=skipped_banned,
        skipped_duplicates=skipped_duplicates,
        jobs=jobs,
    )


@router.get("/stats", summary="Per-site acquisition summary")
async def get_acquisition_stats(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ProductLink))
    all_links = list(result.scalars().all())

    site_map: dict[str, dict] = {}
    for domain_key, support_status in SUPPORTED_SITES.items():
        site_map[domain_key] = {
            "domain": domain_key,
            "support_status": support_status,
            "total": 0,
            "pending": 0,
            "scraping": 0,
            "scraped": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "failed_breakdown": {},
        }

    displayed_domains = set(SUPPORTED_SITES.keys())

    for link in all_links:
        domain = _domain_from_url(link.url)
        if domain not in displayed_domains:
            continue
        entry = site_map[domain]
        entry["total"] += 1
        status = link.status
        if status in entry:
            entry[status] += 1
        if status in ("failed", "error") and link.failure_type:
            breakdown = entry["failed_breakdown"]
            ft = link.failure_type or "unknown"
            breakdown[ft] = breakdown.get(ft, 0) + 1

    for entry in site_map.values():
        if entry["total"] > 0:
            entry["success_rate"] = round(
                (entry["completed"] + entry["scraped"]) / entry["total"], 4
            )
        else:
            entry["success_rate"] = None

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await session.execute(
        select(ProductLink).where(ProductLink.created_at >= today_start)
    )
    today_links = list(today_result.scalars().all())
    today_site: dict[str, int] = {}
    for link in today_links:
        domain = _domain_from_url(link.url)
        if domain in displayed_domains:
            today_site[domain] = today_site.get(domain, 0) + 1

    for entry in site_map.values():
        entry["today_count"] = today_site.get(entry["domain"], 0)

    return {
        "sites": sorted(site_map.values(), key=lambda s: s["domain"]),
        "totals": {
            "total_products": len(all_links),
            "today_products": len(today_links),
            "pending": sum(s["pending"] for s in site_map.values()),
            "scraping": sum(s["scraping"] for s in site_map.values()),
            "scraped": sum(s["scraped"] for s in site_map.values()),
            "completed": sum(s["completed"] for s in site_map.values()),
            "failed": sum(s["failed"] for s in site_map.values()),
        },
    }


@router.get("/jobs", summary="Recent scrape jobs")
async def get_recent_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(ProductLink)
    count_query = select(func.count(ProductLink.id))

    conditions = []
    if status:
        conditions.append(ProductLink.status == status)

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    query = query.order_by(desc(ProductLink.updated_at)).limit(limit).offset(offset)
    result = await session.execute(query)
    links = list(result.scalars().all())

    jobs_list = []
    for link in links:
        domain = _domain_from_url(link.url)
        jobs_list.append({
            "id": link.id,
            "job_id": link.job_id,
            "url": link.url,
            "domain": domain,
            "site": domain,
            "status": link.status,
            "product_name": link.product_name or "",
            "image_count": link.scraped_image_count or 0,
            "error_message": link.error_message or "",
            "failure_type": link.failure_type or "",
            "created_at": link.created_at.isoformat() if link.created_at else None,
            "updated_at": link.updated_at.isoformat() if link.updated_at else None,
            "completed_at": link.completed_at.isoformat() if link.completed_at else None,
        })

    return {
        "jobs": jobs_list,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
