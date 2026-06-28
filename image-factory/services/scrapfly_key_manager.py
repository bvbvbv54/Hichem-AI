from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from configs.logging import get_logger

logger = get_logger(__name__)

# Reset-date override per key (optional). Keys not listed use `_infer_reset_date()`.
_KEY_RESET_DATES: dict[str, str] = {}


def _infer_reset_date(key: str) -> str:
    """Infer a plausible reset date for keys without a hardcoded one: 30 days from now."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")


async def get_all_keys(session: AsyncSession) -> list[str]:
    from database.models.setting import Setting
    result = await session.execute(
        select(Setting).where(Setting.key.like("scrapfly_key_%")).order_by(Setting.key)
    )
    settings = result.scalars().all()
    db_keys = []
    for s in settings:
        if not s.value:
            continue
        db_keys.append(s.value)
    return db_keys


async def add_key(key: str, session: AsyncSession) -> bool:
    from database.models.setting import Setting
    from services.notifications import send_notification

    key_id = f"scrapfly_key_{key[:16]}"
    existing = await session.execute(
        select(Setting).where(Setting.key == key_id)
    )
    is_new = False
    if existing.scalar_one_or_none():
        existing.scalar_one().value = key
    else:
        setting = Setting(key=key_id, value=key)
        session.add(setting)
        is_new = True
    await session.commit()

    # Notify about the new key
    try:
        await send_notification(
            title="Scrapfly API Key Added",
            message=f"New Scrapfly key added (preview: {key[:20]}...). "
                    f"Scraping will resume using this key.",
            level="info",
            type="scrapfly_key_added",
        )
    except Exception as e:
        logger.warning("scrapfly_key_add_notification_failed", error=str(e))

    return is_new


async def remove_key(key: str, session: AsyncSession) -> None:
    from database.models.setting import Setting
    from services.notifications import send_notification

    await session.execute(
        sql_delete(Setting).where(
            Setting.key.like("scrapfly_key_%"),
            Setting.value == key,
        )
    )
    await session.commit()

    try:
        await send_notification(
            title="Scrapfly API Key Removed",
            message=f"Scrapfly key removed (preview: {key[:20]}...).",
            level="warning",
            type="scrapfly_key_removed",
        )
    except Exception as e:
        logger.warning("scrapfly_key_remove_notification_failed", error=str(e))


async def notify_quota_exhausted(redis: Any) -> None:
    """Send notification when all Scrapfly keys are exhausted."""
    from services.notifications import send_notification

    try:
        # Avoid spamming — only notify once per hour
        last_key = "scrapfly:quota_notified_at"
        last = await redis.get(last_key) if redis else None
        if last:
            try:
                last_ts = float(last)
                if time.time() - last_ts < 3600:
                    return
            except (ValueError, TypeError):
                pass

        await send_notification(
            title="Scrapfly Quota Exhausted",
            message="All Scrapfly API keys have reached their quota. "
                    "Scraping is paused until a new key is added or existing keys reset.",
            level="error",
            type="scrapfly_quota_exhausted",
        )
        if redis:
            await redis.set(last_key, str(time.time()))
    except Exception as e:
        logger.warning("scrapfly_quota_notification_failed", error=str(e))


async def mark_key_unauthorized(key: str, redis: Any) -> None:
    """Mark a key as unauthorized (401) so it gets retried after its reset date."""
    key_short = key[:20]
    try:
        if redis:
            await redis.setex(f"scrapfly:unauthorized:{key_short}", 86400 * 7, "1")
            logger.info("scrapfly_key_marked_unauthorized", key=key_short)

        from services.notifications import send_notification
        await send_notification(
            title="Scrapfly Key Unauthorized",
            message=f"Scrapfly key ({key_short}...) returned 401 Unauthorized. "
                    f"It will be retried after its reset date.",
            level="warning",
            type="scrapfly_key_unauthorized",
        )
    except Exception as e:
        logger.warning("scrapfly_unauthorized_notification_failed", error=str(e))


async def retry_unauthorized_keys(redis: Any) -> list[str]:
    """Check if any previously unauthorized keys are past their reset date and should be retried."""
    revived: list[str] = []
    try:
        if not redis:
            return revived
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="scrapfly:unauthorized:*")
            for k in keys:
                key_name = k.decode() if isinstance(k, bytes) else k
                ttl = await redis.ttl(key_name)
                if ttl <= 0:
                    # TTL expired — remove the flag and revive
                    await redis.delete(key_name)
                    revived.append(key_name.replace("scrapfly:unauthorized:", ""))
            if cursor == 0:
                break
        if revived:
            logger.info("scrapfly_unauthorized_keys_revived", count=len(revived))
    except Exception as e:
        logger.warning("scrapfly_retry_unauthorized_error", error=str(e))
    return revived


async def get_keys_with_usage(session: AsyncSession, redis: Any) -> list[dict]:
    import time
    keys = await get_all_keys(session)
    result = []
    for idx, key in enumerate(keys):
        short = key[:20]
        safe_label = f"Key-{idx + 1}"
        used = 0
        remaining: int | None = None
        try:
            r = await redis.hget("scrapfly:usage", f"{short}:cost")
            used = int(r) if r else 0
            r2 = await redis.hget("scrapfly:usage", f"{short}:remaining")
            if r2:
                remaining = int(r2)
        except Exception:
            pass
        estimated_scrapes = None
        cost_per_scrape = 12
        if remaining is not None:
            estimated_scrapes = max(0, remaining // cost_per_scrape)
        result.append({
            "safe_label": safe_label,
            "used": used,
            "remaining": remaining,
            "estimated_scrapes": estimated_scrapes,
            "cost_per_scrape_estimate": cost_per_scrape,
        })
    return result
