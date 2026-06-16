from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CheckResult:
    component: str
    status: str  # "healthy" | "warning" | "offline"
    message: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class SystemChecker:
    """Validates connectivity and health of all system components."""

    async def run_all(self) -> list[CheckResult]:
        async def wrap_timeout(coro, component):
            try:
                return await asyncio.wait_for(coro, timeout=3.5)
            except asyncio.TimeoutError:
                return CheckResult(component, "offline", "Check timed out after 3.5s")
            except Exception as e:
                return CheckResult(component, "offline", f"Check error: {str(e)}")

        checks = [
            wrap_timeout(self.check_api(), "api"),
            wrap_timeout(self.check_database(), "database"),
            wrap_timeout(self.check_redis(), "redis"),
            wrap_timeout(self.check_worker(), "worker"),
            wrap_timeout(self.check_storage(), "storage"),
            wrap_timeout(self.check_delivery(), "delivery"),
            wrap_timeout(self.check_ai_provider(), "ai_provider"),
            wrap_timeout(self.check_queue(), "queue"),
        ]
        return await asyncio.gather(*checks)

    async def check_api(self) -> CheckResult:
        start = time.time()
        try:
            from api.app import app
            latency = (time.time() - start) * 1000
            return CheckResult("api", "healthy", "API is running", latency)
        except Exception as e:
            return CheckResult("api", "offline", str(e))

    async def check_database(self) -> CheckResult:
        start = time.time()
        try:
            from database.session import engine
            async with engine.begin() as conn:
                result = await conn.execute("SELECT 1")
                await result.close()
            latency = (time.time() - start) * 1000
            return CheckResult("database", "healthy", "PostgreSQL connected", latency)
        except Exception as e:
            logger.error("database_check_failed", error=str(e))
            return CheckResult("database", "offline", f"Database error: {str(e)}", details={"error": str(e)})

    async def check_redis(self) -> CheckResult:
        start = time.time()
        try:
            import redis.asyncio as redis_async
            r = redis_async.from_url(settings.redis_url, socket_connect_timeout=5)
            pong = await r.ping()
            await r.aclose()
            latency = (time.time() - start) * 1000
            if pong:
                return CheckResult("redis", "healthy", "Redis connected", latency)
            return CheckResult("redis", "offline", "Redis ping failed")
        except Exception as e:
            return CheckResult("redis", "offline", f"Redis error: {e}", details={"error": str(e)})

    async def check_storage(self) -> CheckResult:
        start = time.time()
        try:
            from services.storage.local import get_storage_backend
            backend = get_storage_backend()
            exists = await backend.exists("/tmp")
            latency = (time.time() - start) * 1000
            return CheckResult("storage", "healthy" if exists else "warning", "Storage accessible", latency)
        except Exception as e:
            return CheckResult("storage", "offline", f"Storage error: {e}", details={"error": str(e)})

    async def check_delivery(self) -> CheckResult:
        start = time.time()
        try:
            from services.delivery.local import create_delivery_backends
            backends = create_delivery_backends()
            healthy = all(b.check_health() for b in backends)
            latency = (time.time() - start) * 1000
            if healthy:
                return CheckResult("delivery", "healthy", f"{len(backends)} delivery backend(s) ready", latency)
            return CheckResult("delivery", "warning", "Some delivery backends unhealthy", latency)
        except Exception as e:
            return CheckResult("delivery", "offline", f"Delivery error: {e}", details={"error": str(e)})

    async def check_ai_provider(self) -> CheckResult:
        start = time.time()
        try:
            from services.nano_banana.client import NanoBananaClient
            provider = NanoBananaClient()
            healthy = await provider.check_health()
            latency = (time.time() - start) * 1000
            if healthy:
                return CheckResult("ai_provider", "healthy", f"Provider '{settings.image_provider}' reachable", latency)
            return CheckResult("ai_provider", "warning", f"Provider '{settings.image_provider}' health check failed", latency)
        except Exception as e:
            return CheckResult("ai_provider", "offline", f"Provider error: {e}", details={"error": str(e)})

    async def check_worker(self) -> CheckResult:
        """Check if Celery worker is active and responsive."""
        start = time.time()
        try:
            import redis.asyncio as redis_async
            r = redis_async.from_url(settings.celery_broker_url, socket_connect_timeout=5)
            
            # Check if there are workers registered
            workers = await r.execute_command("GET", "celery:workers")
            
            # Check broker connectivity
            await r.ping()
            await r.aclose()
            
            latency = (time.time() - start) * 1000
            if workers:
                return CheckResult("worker", "healthy", "Celery worker(s) active", latency)
            else:
                return CheckResult("worker", "warning", "Celery broker ready, waiting for worker", latency)
        except Exception as e:
            logger.error("worker_check_failed", error=str(e))
            return CheckResult("worker", "offline", f"Worker error: {str(e)}", details={"error": str(e)})

    async def check_queue(self) -> CheckResult:
        start = time.time()
        try:
            import redis.asyncio as redis_async
            r = redis_async.from_url(settings.celery_broker_url, socket_connect_timeout=5)
            pong = await r.ping()
            await r.aclose()
            latency = (time.time() - start) * 1000
            if pong:
                return CheckResult("queue", "healthy", "Message queue (Redis) connected", latency)
            return CheckResult("queue", "offline", "Message queue check failed")
        except Exception as e:
            logger.error("queue_check_failed", error=str(e))
            return CheckResult("queue", "offline", f"Queue error: {str(e)}", details={"error": str(e)})
