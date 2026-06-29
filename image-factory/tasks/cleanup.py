from __future__ import annotations

from workers.celery_app import celery_app
from configs.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=0, acks_late=True)
def run_local_cleanup(self):
    import asyncio
    from database.session import async_session
    from services.cleanup import run_cleanup

    async def _run():
        async with async_session() as session:
            return await run_cleanup(session, dry_run=False)

    result = asyncio.run(_run())
    logger.info("periodic_cleanup_complete", **result)
    return result
