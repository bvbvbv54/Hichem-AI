from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import MarketplaceSession

logger = get_logger(__name__)

SESSION_KEY_PREFIX = "intel:session:"
SESSION_INDEX_PREFIX = "intel:sessions:"
SESSION_POOL_KEY = "intel:session_pool:"
SESSION_HEALTH_KEY = "intel:session_health:"


class SessionStore:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def create_session(self, marketplace: str, user_agent: str = "") -> MarketplaceSession:
        redis_conn = await self._get_redis()
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        session = MarketplaceSession(
            id=session_id,
            marketplace=marketplace,
            user_agent=user_agent,
            created_at=now,
            last_used=now,
        )
        key = f"{SESSION_KEY_PREFIX}{session_id}"
        await redis_conn.set(key, json.dumps(session.to_dict()), ex=86400 * 7)
        await redis_conn.sadd(f"{SESSION_INDEX_PREFIX}{marketplace}", session_id)
        await redis_conn.expire(f"{SESSION_INDEX_PREFIX}{marketplace}", 86400 * 7)
        logger.info("session_created", session_id=session_id, marketplace=marketplace)
        return session

    async def get_session(self, session_id: str) -> MarketplaceSession | None:
        redis_conn = await self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session_id}"
        data = await redis_conn.get(key)
        if not data:
            return None
        try:
            parsed = json.loads(data)
            return MarketplaceSession.from_dict(parsed)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("session_deserialize_failed", session_id=session_id, error=str(exc))
            return None

    async def save_session(self, session: MarketplaceSession) -> None:
        redis_conn = await self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session.id}"
        await redis_conn.set(key, json.dumps(session.to_dict()), ex=86400 * 7)
        await redis_conn.sadd(f"{SESSION_INDEX_PREFIX}{session.marketplace}", session.id)
        await redis_conn.expire(f"{SESSION_INDEX_PREFIX}{session.marketplace}", 86400 * 7)

    async def get_sessions_for_marketplace(self, marketplace: str) -> list[MarketplaceSession]:
        redis_conn = await self._get_redis()
        index_key = f"{SESSION_INDEX_PREFIX}{marketplace}"
        session_ids = await redis_conn.smembers(index_key)
        if not session_ids:
            return []
        sessions: list[MarketplaceSession] = []
        for sid in session_ids:
            sid_str = sid.decode() if isinstance(sid, bytes) else sid
            session = await self.get_session(sid_str)
            if session:
                sessions.append(session)
        return sessions

    async def get_active_sessions(self, marketplace: str) -> list[MarketplaceSession]:
        sessions = await self.get_sessions_for_marketplace(marketplace)
        return [s for s in sessions if s.is_active]

    async def get_best_session(self, marketplace: str) -> MarketplaceSession | None:
        sessions = await self.get_active_sessions(marketplace)
        if not sessions:
            return None
        sessions.sort(key=lambda s: s.trust_score, reverse=True)
        return sessions[0]

    async def get_healthy_session_count(self, marketplace: str) -> int:
        sessions = await self.get_active_sessions(marketplace)
        return sum(1 for s in sessions if s.trust_score >= 0)

    async def deactivate_session(self, session_id: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.is_active = False
            await self.save_session(session)

    async def delete_session(self, session_id: str) -> None:
        redis_conn = await self._get_redis()
        session = await self.get_session(session_id)
        if session:
            key = f"{SESSION_KEY_PREFIX}{session_id}"
            await redis_conn.delete(key)
            await redis_conn.srem(f"{SESSION_INDEX_PREFIX}{session.marketplace}", session_id)

    async def get_all_marketplaces(self) -> list[str]:
        redis_conn = await self._get_redis()
        keys = await redis_conn.keys(f"{SESSION_INDEX_PREFIX}*")
        marketplaces: set[str] = set()
        for key in keys:
            k = key.decode() if isinstance(key, bytes) else key
            marketplace = k.replace(SESSION_INDEX_PREFIX, "")
            if marketplace:
                marketplaces.add(marketplace)
        return sorted(marketplaces)

    async def update_trust_score(self, session_id: str, delta: float) -> None:
        session = await self.get_session(session_id)
        if session:
            session.trust_score = max(-100.0, min(100.0, session.trust_score + delta))
            await self.save_session(session)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
