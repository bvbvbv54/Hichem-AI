from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from configs.settings import settings
from configs.logging import setup_logging, get_logger
from database.session import init_db, close_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting_api", app=settings.app_name, version=settings.app_version)
    await init_db()
    yield
    await close_db()
    logger.info("shutdown_api")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.middleware.auth import AuthMiddleware, RateLimitMiddleware
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)

    from api.routes.health import router as health_router
    from api.routes.generation import router as generation_router
    from api.routes.jobs import router as jobs_router
    from api.routes.templates import router as templates_router
    from api.routes.products import router as products_router
    from api.routes.auth import router as auth_router
    from api.routes.users import router as users_router
    from api.routes.projects import router as projects_router
    from api.routes.assets import router as assets_router
    from api.routes.analytics import router as analytics_router
    from api.routes.admin import router as admin_router
    from api.routes.dashboard import router as dashboard_router
    from api.routes.events import router as events_router
    from api.routes.verification import router as verification_router
    from api.routes.consumption import router as consumption_router
    from api.routes.google_drive import router as google_drive_router
    from api.routes.content import router as content_router
    from api.routes.credits import router as credits_router
    from api.routes.scrapfly_admin_page import router as scrapfly_page_router
    from api.routes.notifications import router as notifications_router
    from api.routes.acquisition import router as acquisition_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(generation_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(templates_router, prefix="/api/v1")
    app.include_router(products_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(consumption_router, prefix="/api/v1")
    app.include_router(google_drive_router, prefix="/api/v1")
    app.include_router(content_router, prefix="/api/v1")
    app.include_router(credits_router, prefix="/api/v1")
    app.include_router(scrapfly_page_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(acquisition_router, prefix="/api/v1")

    return app


app = create_app()
