from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from configs.settings import settings

_engine: Any = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            echo=settings.debug,
        )
    return _engine


engine = get_engine()


class _LazySession:
    _smaker: Any = None

    def __call__(self):
        if self._smaker is None:
            self._smaker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
        return self._smaker()


async_session = _LazySession()


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    for attempt in range(3):
        try:
            async with get_engine().begin() as conn:
                from database.models.job import Job  # noqa
                from database.models.asset import Asset  # noqa
                from database.models.user import User, ApiKey, Project  # noqa
                from database.models.product_link import ProductLink  # noqa
                from database.models.notification import Notification  # noqa
                from database.models.setting import Setting  # noqa
                from database.models.feature_cache import FeatureCache  # noqa
                from database.models.correction_event import CorrectionEvent  # noqa
                from database.models.learning_weight import LearningWeight  # noqa

                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(1)


async def close_db() -> None:
    engine = get_engine()
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, Any]:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
