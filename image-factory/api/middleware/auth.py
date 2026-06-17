from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, status
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from configs.settings import settings


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        from starlette.requests import Request
        request = Request(scope, receive)

        if request.method == "OPTIONS":
            return await self.app(scope, receive, send)

        public_paths = ("/docs", "/redoc", "/openapi.json", "/api/v1/health", "/api/v1/health/ready")
        public_prefixes = ("/api/v1/auth", "/api/v1/events", "/api/v1/verification", "/api/v1/dashboard", "/api/v1/assets", "/api/v1/consumption", "/api/v1/credits")
        if request.url.path in public_paths or any(request.url.path.startswith(p) for p in public_prefixes):
            return await self.app(scope, receive, send)

        api_key = request.headers.get("X-API-Key")
        if api_key:
            if api_key == settings.api_key:
                return await self.app(scope, receive, send)
            response = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid API key"},
            )
            await response(scope, receive, send)
            return

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token:
                return await self.app(scope, receive, send)

        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid authentication. Provide X-API-Key or Authorization: Bearer <token>"},
        )
        await response(scope, receive, send)


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self._requests: dict[str, list[float]] = defaultdict(list)
        self.max_requests = settings.api_rate_limit
        self.window = settings.api_rate_limit_period

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        from starlette.requests import Request
        request = Request(scope, receive)

        if request.url.path in ("/docs", "/redoc", "/openapi.json", "/api/v1/health"):
            return await self.app(scope, receive, send)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window

        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
            await response(scope, receive, send)
            return

        self._requests[client_ip].append(now)
        await self.app(scope, receive, send)
