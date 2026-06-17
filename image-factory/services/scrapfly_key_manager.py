from __future__ import annotations

from typing import Any

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from configs.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_KEYS = [
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
    "SCRAPFLY_KEY_REDACTED",
]


async def get_all_keys(session: AsyncSession) -> list[str]:
    from database.models.setting import Setting
    result = await session.execute(
        select(Setting).where(Setting.key.like("scrapfly_key_%")).order_by(Setting.key)
    )
    settings = result.scalars().all()
    db_keys = [s.value for s in settings if s.value]
    if db_keys:
        return db_keys
    return list(_FALLBACK_KEYS)


async def add_key(key: str, session: AsyncSession) -> None:
    from database.models.setting import Setting
    key_id = f"scrapfly_key_{key[:16]}"
    existing = await session.execute(
        select(Setting).where(Setting.key == key_id)
    )
    if existing.scalar_one_or_none():
        existing.scalar_one().value = key
    else:
        setting = Setting(key=key_id, value=key)
        session.add(setting)
    await session.commit()


async def remove_key(key: str, session: AsyncSession) -> None:
    from database.models.setting import Setting
    await session.execute(
        sql_delete(Setting).where(
            Setting.key.like("scrapfly_key_%"),
            Setting.value == key,
        )
    )
    await session.commit()


async def get_keys_with_usage(session: AsyncSession, redis: Any) -> list[dict]:
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
            # remaining is ACCOUNT-level, not per-key. Only set if we've made a request with this key.
            if r2:
                remaining = int(r2)
        except Exception:
            pass
        result.append({
            "key_preview": short + "...",
            "full_key": key,
            "used": used,
            "remaining": remaining,  # None = untracked (no request made with this key yet)
        })
    return result
