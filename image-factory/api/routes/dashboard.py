from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from api.dependencies import get_redis
from database.session import get_session
from database.models.job import Job
from database.models.asset import Asset
from database.models.product_link import ProductLink
from configs.logging import get_logger
from configs.settings import settings
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

    scraped_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status == "scraped"))
    scraped_count = scraped_result.scalar() or 0

    completed_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status == "completed"))
    completed = completed_result.scalar() or 0

    failed_result = await session.execute(select(func.count(ProductLink.id)).where(ProductLink.status.in_(["failed", "error"])))
    failed = failed_result.scalar() or 0

    ai_images_result = await session.execute(select(func.count(Asset.id)))
    ai_images = ai_images_result.scalar() or 0
    scraped_images_result = await session.execute(
        select(func.coalesce(func.sum(ProductLink.scraped_image_count), 0))
    )
    scraped_images = scraped_images_result.scalar() or 0
    total_images = ai_images + scraped_images

    try:
        balancer = get_credit_balancer()
        balance = await balancer.check_balance(session)
        cost_per_image = balancer.COST_PER_IMAGE_CENTS
        total_cost_cents = total_images * cost_per_image
    except Exception as e:
        logger.warning("credit_balancer_unavailable", error=str(e))
        balance = 0.0
        cost_per_image = 1.0
        total_cost_cents = 0.0

    # Avg time: always calculate from historical completed jobs
    completed_jobs_result = await session.execute(
        select(Job).where(Job.status == "completed", Job.completed_at.isnot(None), Job.created_at.isnot(None))
    )
    completed_jobs = completed_jobs_result.scalars().all()
    if completed_jobs:
        times = [(j.completed_at - j.created_at).total_seconds() for j in completed_jobs if j.completed_at and j.created_at]
        avg_time = round(sum(times) / len(times), 1) if times else 0
    else:
        avg_time = 0

    active_processing_jobs = await session.execute(
        select(func.count(Job.id)).where(Job.status.in_(["processing", "generating", "storing", "delivering"]))
    )
    products_processing = active_processing_jobs.scalar() or 0

    # Weighted completion: scraped=50%, completed=100%
    if total > 0:
        weighted_pct = round(((scraped_count * 50 + completed * 100) / (total * 100)) * 100)
    else:
        weighted_pct = 0

    return {
        "total_products": total,
        "products_in_queue": in_queue,
        "products_processing": products_processing,
        "products_scraped": scraped_count,
        "products_completed": completed,
        "products_failed": failed,
        "total_images": total_images,
        "ai_images": ai_images,
        "scraped_images": scraped_images,
        "ai_credits_used": ai_images * cost_per_image,
        "estimated_cost": ai_images * cost_per_image,
        "nano_banana_balance": balance,
        "nano_banana_cost_per_image": cost_per_image,
        "avg_processing_time_seconds": avg_time,
        "completion_percentage": weighted_pct,
        "scraped_count": scraped_count,
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


@router.get("/ai-limiter")
async def get_ai_limiter(session: AsyncSession = Depends(get_session)):
    from services.nano_banana.credit_balancer import get_credit_balancer
    from services.settings_service import get_setting
    balancer = get_credit_balancer()
    budget_cents = float(settings.monthly_budget_cents)
    db_budget = await get_setting("monthly_budget_cents", session, "")
    if db_budget:
        budget_cents = float(db_budget)
    usage_cents = await balancer.get_total_usage_cents(session)
    remaining_cents = max(0, budget_cents - usage_cents)
    pct = round((usage_cents / budget_cents) * 100, 1) if budget_cents > 0 else 0
    total_assets = await session.execute(select(func.count(Asset.id)))
    return {
        "monthly_budget_dollars": round(budget_cents / 100, 2),
        "usage_dollars": round(usage_cents / 100, 2),
        "remaining_dollars": round(remaining_cents / 100, 2),
        "usage_percent": pct,
        "total_images_this_month": total_assets.scalar() or 0,
        "cost_per_image_dollars": balancer.COST_PER_IMAGE_CENTS / 100,
        "low_credits": remaining_cents < balancer.LOW_CREDIT_THRESHOLD_CENTS,
        "critical_credits": remaining_cents < balancer.CRITICAL_CREDIT_THRESHOLD_CENTS,
    }


@router.get("/captcha")
async def get_captcha_intelligence(redis: aioredis.Redis = Depends(get_redis)):
    captcha_stats_prefix = "intel:captcha_stats:"
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    top: list[dict] = []
    total_today = 0
    total_all_time = 0

    # Scan keys matching the pattern
    cursor = 0
    domains_seen: set[str] = set()
    while True:
        cursor, keys = await redis.scan(cursor, match=f"{captcha_stats_prefix}*:*", count=500)
        for key in keys:
            k = key.decode() if isinstance(key, bytes) else key
            parts = k.split(":")
            if len(parts) >= 3:
                domain = parts[2]
                day = parts[3] if len(parts) >= 4 else ""
                domains_seen.add(domain)
        if cursor == 0:
            break

    for domain in sorted(domains_seen):
        # Get today's count
        today_key = f"{captcha_stats_prefix}{domain}:{date_str}"
        today_stats = await redis.hgetall(today_key)
        today_total = 0
        if today_stats:
            for k, v in today_stats.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = int(v.decode() if isinstance(v, bytes) else v)
                if key == "total":
                    today_total = val
        total_today += today_total

        # Get 7-day count
        week_total = 0
        for i in range(7):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            wk_key = f"{captcha_stats_prefix}{domain}:{d}"
            wk_stats = await redis.hgetall(wk_key)
            if wk_stats:
                for k, v in wk_stats.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    val = int(v.decode() if isinstance(v, bytes) else v)
                    if key == "total":
                        week_total += val

        if week_total > 0:
            top.append({"domain": domain, "captcha_count": week_total})

        # Get all-time count for this domain
        domain_cursor = 0
        while True:
            domain_cursor, domain_keys = await redis.scan(domain_cursor, match=f"{captcha_stats_prefix}{domain}:*", count=500)
            for dk in domain_keys:
                dk_str = dk.decode() if isinstance(dk, bytes) else dk
                stats = await redis.hgetall(dk_str)
                if stats:
                    for k, v in stats.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = int(v.decode() if isinstance(v, bytes) else v)
                        if key == "total":
                            total_all_time += val
            if domain_cursor == 0:
                break

    top.sort(key=lambda x: x["captcha_count"], reverse=True)
    top = top[:10]

    return {
        "top_blocking_marketplaces": top,
        "daily_report": {entry["domain"]: {"total_captchas": entry["captcha_count"]} for entry in top},
        "total_captchas_today": total_today,
        "total_captchas_all_time": total_all_time,
    }
