from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from configs.logging import get_logger

logger = get_logger(__name__)

# Per-key reset dates (YYYY-MM-DD). After this date the key is re-enabled.
# Update these when a key's billing period resets.
_KEY_RESET_DATES: dict[str, str] = {
    "SCRAPFLY_KEY_REDACTED": "2026-08-17",
    "SCRAPFLY_KEY_REDACTED": "2026-07-17",
    "SCRAPFLY_KEY_REDACTED": "2026-07-17",
    "SCRAPFLY_KEY_REDACTED": "2026-07-17",
    "SCRAPFLY_KEY_REDACTED": "2026-07-27",
    "SCRAPFLY_KEY_REDACTED": "2026-07-27",
    "SCRAPFLY_KEY_REDACTED": "2026-07-27",
    "SCRAPFLY_KEY_REDACTED": "2026-07-27",
}

_FALLBACK_KEYS = [
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
]

# Keys permanently deprecated (wrong account, revoked, etc.) — never revived.
_PERMANENTLY_DEAD: set[str] = set()

DEAD_KEYS: set[str] = {
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
}


def _is_key_past_reset(key: str) -> bool:
    """Check if a key's reset date has passed, meaning it should be re-enabled."""
    reset_str = _KEY_RESET_DATES.get(key)
    if not reset_str:
        return False
    try:
        reset_date = datetime.strptime(reset_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= reset_date
    except (ValueError, TypeError):
        return False


def _get_keys_for_date() -> list[str]:
    """Return fallback keys, excluding permanently dead ones and reviving past-reset keys."""
    today = datetime.now(timezone.utc)
    result = []
    for key in _FALLBACK_KEYS:
        if key in _PERMANENTLY_DEAD:
            continue
        # If the key is in DEAD_KEYS but past its reset date, revive it
        if key in DEAD_KEYS and _is_key_past_reset(key):
            logger.info("scrapfly_key_revived_after_reset", key=key[:20])
            DEAD_KEYS.discard(key)
            result.append(key)
        elif key not in DEAD_KEYS:
            result.append(key)
    return result


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
        if s.value in _PERMANENTLY_DEAD:
            continue
        # Revive past-reset keys
        if s.value in DEAD_KEYS and _is_key_past_reset(s.value):
            logger.info("scrapfly_key_revived_after_reset_db", key=s.value[:20])
            DEAD_KEYS.discard(s.value)
            db_keys.append(s.value)
        elif s.value not in DEAD_KEYS:
            db_keys.append(s.value)
    if db_keys:
        return db_keys
    return _get_keys_for_date()


async def add_key(key: str, session: AsyncSession) -> bool:
    from database.models.setting import Setting
    from services.notifications import send_notification
    from database.session import async_session

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

    # Revive from dead keys if it was previously marked dead
    if key in DEAD_KEYS:
        DEAD_KEYS.discard(key)
        logger.info("scrapfly_key_removed_from_dead", key=key[:20])

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
            # Store the unauthorized status with a TTL until the reset date
            reset_str = _KEY_RESET_DATES.get(key)
            if reset_str:
                try:
                    reset_date = datetime.strptime(reset_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    ttl = int((reset_date - datetime.now(timezone.utc)).total_seconds())
                    if ttl > 0:
                        await redis.setex(f"scrapfly:unauthorized:{key_short}", ttl, "1")
                except (ValueError, TypeError):
                    await redis.setex(f"scrapfly:unauthorized:{key_short}", 86400 * 31, "1")
            else:
                await redis.setex(f"scrapfly:unauthorized:{key_short}", 86400 * 7, "1")
            DEAD_KEYS.add(key)
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
                short = key_name.replace("scrapfly:unauthorized:", "")
                ttl = await redis.ttl(key_name)
                if ttl <= 0:
                    # TTL expired — remove the flag and revive
                    await redis.delete(key_name)
                    DEAD_KEYS.discard(short)
                    revived.append(short)
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
    for key in keys:
        short = key[:20]
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
            "key_preview": short + "...",
            "full_key": key,
            "used": used,
            "remaining": remaining,
            "estimated_scrapes": estimated_scrapes,
            "cost_per_scrape_estimate": cost_per_scrape,
        })
    return result
