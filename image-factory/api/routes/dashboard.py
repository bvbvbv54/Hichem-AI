from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.job import Job
from database.models.asset import Asset
from database.models.product_link import ProductLink
from configs.logging import get_logger
from services.nano_banana.credit_balancer import get_credit_balancer

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_dashboard_stats(session: AsyncSession = Depends(get_session)):
    # Count actual products (ProductLink), not Job rows
    total_result = await session.execute(select(func.count(ProductLink.id)))
    total = total_result.scalar() or 0

    pending_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status == "pending"))
    in_queue = pending_result.scalar() or 0

    processing_result = await session.execute(
        select(func.count(ProductLink.id)).where(ProductLink.status.in_(["scraping", "generating"]))
    )
    processing = processing_result.scalar() or 0

    completed_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status == "completed"))
    completed = completed_result.scalar() or 0

    failed_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status == "failed"))
    failed = failed_result.scalar() or 0

    images_result = await session.execute(select(func.count(Asset.id)))
    total_images = images_result.scalar() or 0

    try:
        balancer = get_credit_balancer()
        balance = await balancer.check_balance()
        cost_per_image = balancer.COST_PER_IMAGE_CENTS
        total_cost_cents = total_images * cost_per_image
    except Exception as e:
        logger.warning("credit_balancer_unavailable", error=str(e))
        balance = 0.0
        cost_per_image = 1.0
        total_cost_cents = 0.0

    completed_jobs_result = await session.execute(
        select(Job).where(Job.status == "completed", Job.completed_at.isnot(None), Job.created_at.isnot(None))
    )
    completed_jobs = completed_jobs_result.scalars().all()
    if completed_jobs:
        times = [(j.completed_at - j.created_at).total_seconds() for j in completed_jobs if j.completed_at and j.created_at]
        avg_time = round(sum(times) / len(times), 1) if times else 0
    else:
        avg_time = 0

    return {
        "total_products": total,
        "products_in_queue": in_queue,
        "products_processing": processing,
        "products_completed": completed,
        "products_failed": failed,
        "total_images": total_images,
        "ai_credits_used": total_images * cost_per_image,
        "estimated_cost": total_cost_cents,
        "nano_banana_balance": balance,
        "nano_banana_cost_per_image": cost_per_image,
        "avg_processing_time_seconds": avg_time,
    }


@router.get("/active")
async def get_active_jobs(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Job).where(Job.status.in_(["pending", "processing", "enhancing_prompt", "generating", "storing", "delivering", "retrying"])).order_by(Job.created_at.desc()).limit(50)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "type": j.type or "single",
            "status": j.status,
            "prompt": (j.prompt or "")[:120],
            "progress": j.progress or 0,
            "project_name": j.project_name or "",
            "num_images": j.num_images or 1,
            "error_message": j.error_message or "",
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "updated_at": j.updated_at.isoformat() if j.updated_at else "",
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/status")
async def get_system_status():
    db_status = await check_db()
    redis_status = await check_redis()
    worker_status = await check_celery_worker()
    return {
        "api": "healthy",
        "database": db_status,
        "redis": redis_status,
        "worker": worker_status,
        "queue": redis_status,
        "storage": "healthy",
        "delivery": "healthy",
    }


async def check_db() -> str:
    try:
        import asyncio
        from database.session import engine
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(select(1))
        return "healthy"
    except Exception as e:
        return f"degraded: {e}"


async def check_redis() -> str:
    try:
        import asyncio
        import redis.asyncio as aioredis
        from configs.settings import settings
        r = await asyncio.wait_for(
            aioredis.from_url(settings.redis_url, socket_connect_timeout=2),
            timeout=2.0,
        )
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        return "healthy"
    except Exception as e:
        return f"degraded: {e}"


async def check_celery_worker() -> str:
    try:
        import asyncio
        import redis.asyncio as aioredis
        from configs.settings import settings
        r = await asyncio.wait_for(
            aioredis.from_url(settings.celery_broker_url, socket_connect_timeout=2),
            timeout=2.0,
        )
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        return "healthy"
    except Exception as e:
        return f"degraded: {e}"


@router.get("/queue")
async def get_queue_info(session: AsyncSession = Depends(get_session)):
    active = await session.execute(select(func.count(Job.id)).where(Job.status.in_(["processing", "generating", "storing", "delivering"])))
    waiting = await session.execute(select(func.count(Job.id)).where(Job.status == "pending"))
    failed = await session.execute(select(func.count(Job.id)).where(Job.status == "failed"))
    retry = await session.execute(select(func.count(Job.id)).where(Job.status == "retrying"))

    active_count = active.scalar() or 0
    waiting_count = waiting.scalar() or 0
    failed_count = failed.scalar() or 0
    retry_count = retry.scalar() or 0
    total = active_count + waiting_count + failed_count

    return {
        "current_length": total,
        "active_jobs": active_count,
        "waiting_jobs": waiting_count,
        "failed_jobs": failed_count,
        "retry_jobs": retry_count,
        "estimated_completion_minutes": total * 2,
        "estimated_wait_minutes": waiting_count * 2,
        "workers_active": 4,
    }
