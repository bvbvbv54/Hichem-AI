from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Any

from configs.logging import get_logger
from configs.settings import settings
from services.intelligence.session_store import SessionStore
from services.intelligence.models import MarketplaceSession, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

TRUST_SCORE_SUCCESS_EXTRACT = 5
TRUST_SCORE_SUCCESS_PAGE = 2
TRUST_SCORE_CAPTCHA = -20
TRUST_SCORE_CHALLENGE = -30
TRUST_SCORE_BLOCKED = -25
TRUST_SCORE_REDIRECT = -10
TRUST_SCORE_TIMEOUT = -5
TRUST_SCORE_IMAGES_DOWNLOADED = 3

SESSION_POOL_SIZE_MIN = 2
SESSION_POOL_SIZE_MAX = 10
SESSION_TRUST_THRESHOLD = -50


class SessionManager:
    def __init__(self, store: SessionStore | None = None, emitter: EventEmitter | None = None) -> None:
        self.store = store or SessionStore()
        self.emitter = emitter or EventEmitter()
        self._active_sessions: dict[str, list[MarketplaceSession]] = {}
        self._pool_sizes: dict[str, int] = {}

    async def get_or_create_session(self, marketplace: str, user_agent: str = "") -> MarketplaceSession:
        best = await self.store.get_best_session(marketplace)
        if best:
            best.last_used = datetime.utcnow().isoformat()
            best.session_age = (datetime.utcnow() - datetime.fromisoformat(best.created_at)).total_seconds()
            await self.store.save_session(best)
            await self.emitter.emit(IntelligenceEventType.SESSION_REUSED, marketplace, {
                "session_id": best.id,
                "trust_score": best.trust_score,
                "request_count": best.request_count,
            })
            return best
        session = await self.store.create_session(marketplace, user_agent)
        await self.emitter.emit(IntelligenceEventType.SESSION_CREATED, marketplace, {
            "session_id": session.id,
        })
        return session

    async def record_success(self, session: MarketplaceSession, extracted: bool = True) -> None:
        delta = TRUST_SCORE_SUCCESS_EXTRACT if extracted else TRUST_SCORE_SUCCESS_PAGE
        session.trust_score = max(-100.0, min(100.0, session.trust_score + delta))
        session.request_count += 1
        session.last_success = datetime.utcnow().isoformat()
        session.last_used = datetime.utcnow().isoformat()
        await self.store.save_session(session)
        await self.emitter.emit(IntelligenceEventType.TRUST_SCORE_CHANGED, session.marketplace, {
            "session_id": session.id,
            "delta": delta,
            "new_score": session.trust_score,
            "reason": "success" if extracted else "page_load",
        })

    async def record_failure(self, session: MarketplaceSession, failure_type: str) -> None:
        delta_map = {
            "captcha": TRUST_SCORE_CAPTCHA,
            "challenge": TRUST_SCORE_CHALLENGE,
            "blocked": TRUST_SCORE_BLOCKED,
            "redirect": TRUST_SCORE_REDIRECT,
            "timeout": TRUST_SCORE_TIMEOUT,
        }
        delta = delta_map.get(failure_type, -5)
        session.trust_score = max(-100.0, min(100.0, session.trust_score + delta))
        session.request_count += 1
        session.last_failure = datetime.utcnow().isoformat()
        session.last_used = datetime.utcnow().isoformat()
        if failure_type == "captcha":
            session.captcha_count += 1
        await self.store.save_session(session)
        await self.emitter.emit(IntelligenceEventType.TRUST_SCORE_CHANGED, session.marketplace, {
            "session_id": session.id,
            "delta": delta,
            "new_score": session.trust_score,
            "reason": failure_type,
        })
        if session.trust_score <= SESSION_TRUST_THRESHOLD:
            await self.store.deactivate_session(session.id)
            await self.emitter.emit(IntelligenceEventType.SESSION_EXPIRED, session.marketplace, {
                "session_id": session.id,
                "trust_score": session.trust_score,
                "reason": "trust_threshold_exceeded",
            })
            logger.warning("session_deactivated_low_trust", session_id=session.id, score=session.trust_score)

    async def rotate_session(self, marketplace: str, current_session: MarketplaceSession) -> MarketplaceSession:
        await self.store.deactivate_session(current_session.id)
        await self.emitter.emit(IntelligenceEventType.SESSION_ROTATED, marketplace, {
            "old_session_id": current_session.id,
            "reason": "manual_rotation",
        })
        return await self.get_or_create_session(marketplace)

    async def ensure_pool_size(self, marketplace: str, min_size: int = SESSION_POOL_SIZE_MIN) -> list[MarketplaceSession]:
        sessions = await self.store.get_active_sessions(marketplace)
        if len(sessions) < min_size:
            new_count = min(min_size - len(sessions), SESSION_POOL_SIZE_MAX - len(sessions))
            for _ in range(new_count):
                session = await self.store.create_session(marketplace)
                sessions.append(session)
        return sessions

    async def get_pool_stats(self, marketplace: str) -> dict[str, Any]:
        sessions = await self.store.get_sessions_for_marketplace(marketplace)
        active = [s for s in sessions if s.is_active]
        if not sessions:
            return {
                "marketplace": marketplace,
                "total": 0,
                "active": 0,
                "avg_trust": 0.0,
                "total_requests": 0,
                "total_captchas": 0,
            }
        avg_trust = sum(s.trust_score for s in active) / len(active) if active else 0.0
        return {
            "marketplace": marketplace,
            "total": len(sessions),
            "active": len(active),
            "avg_trust": round(avg_trust, 2),
            "total_requests": sum(s.request_count for s in sessions),
            "total_captchas": sum(s.captcha_count for s in sessions),
        }

    async def close(self) -> None:
        await self.store.close()
