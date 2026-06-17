from __future__ import annotations

from datetime import datetime

from workers.celery_app import celery_app
from workers.async_runner import run_async
from configs.logging import get_logger
from services.intelligence.orchestrator import IntelligenceOrchestrator
from services.intelligence.trend_discovery import TrendDiscoveryEngine
from services.intelligence.session_store import SessionStore
from services.intelligence.captcha_manager import CaptchaManager

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_daily_trend_report(self):
    logger.info("generating_daily_trend_report")
    try:
        run_async(_do_generate_daily_trend_report())
    except Exception as exc:
        logger.error("daily_trend_report_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_weekly_trend_report(self):
    logger.info("generating_weekly_trend_report")
    try:
        run_async(_do_generate_weekly_trend_report())
    except Exception as exc:
        logger.error("weekly_trend_report_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_health_report(self):
    logger.info("generating_health_report")
    try:
        run_async(_do_generate_health_report())
    except Exception as exc:
        logger.error("health_report_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def maintain_sessions(self):
    logger.info("maintaining_sessions")
    try:
        run_async(_do_maintain_sessions())
    except Exception as exc:
        logger.error("session_maintenance_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_captcha_report(self):
    logger.info("generating_captcha_report")
    try:
        run_async(_do_generate_captcha_report())
    except Exception as exc:
        logger.error("captcha_report_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def cleanup_stale_sessions(self):
    logger.info("cleaning_stale_sessions")
    try:
        run_async(_do_cleanup_stale_sessions())
    except Exception as exc:
        logger.error("session_cleanup_failed", error=str(exc))


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_marketplace_opportunity_report(self):
    logger.info("generating_opportunity_report")
    try:
        run_async(_do_generate_opportunity_report())
    except Exception as exc:
        logger.error("opportunity_report_failed", error=str(exc))


async def _do_generate_daily_trend_report():
    engine = TrendDiscoveryEngine()
    try:
        report = await engine.generate_daily_report()
        logger.info("daily_trend_report_complete", categories=len(report.fast_growing_categories))
    finally:
        await engine.close()


async def _do_generate_weekly_trend_report():
    engine = TrendDiscoveryEngine()
    try:
        report = await engine.generate_weekly_report()
        logger.info("weekly_trend_report_complete")
    finally:
        await engine.close()


async def _do_generate_health_report():
    orchestrator = IntelligenceOrchestrator()
    try:
        report = await orchestrator.health_monitor.get_trend_report()
        logger.info("health_report_complete",
            marketplaces=report.get("marketplace_count", 0),
            best=report.get("best_performing", {}).get("marketplace"),
            worst=report.get("worst_performing", {}).get("marketplace"),
        )
    finally:
        await orchestrator.close()


async def _do_maintain_sessions():
    store = SessionStore()
    try:
        marketplaces = await store.get_all_marketplaces()
        for mp in marketplaces:
            sessions = await store.get_sessions_for_marketplace(mp)
            active = [s for s in sessions if s.is_active]
            logger.info("session_pool_status", marketplace=mp, total=len(sessions), active=len(active))
    finally:
        await store.close()


async def _do_generate_captcha_report():
    captcha_mgr = CaptchaManager()
    try:
        blocking = await captcha_mgr.get_top_blocking_marketplaces(10)
        logger.info("captcha_report_complete", top_blocking=blocking[:5] if blocking else [])
    finally:
        await captcha_mgr.close()


async def _do_cleanup_stale_sessions():
    store = SessionStore()
    try:
        marketplaces = await store.get_all_marketplaces()
        cleaned = 0
        for mp in marketplaces:
            sessions = await store.get_sessions_for_marketplace(mp)
            for session in sessions:
                if not session.is_active and session.trust_score < -80:
                    await store.delete_session(session.id)
                    cleaned += 1
        logger.info("stale_sessions_cleaned", count=cleaned)
    finally:
        await store.close()


async def _do_generate_opportunity_report():
    engine = TrendDiscoveryEngine()
    try:
        report = await engine.generate_marketplace_opportunity_report()
        logger.info("opportunity_report_complete", patterns=len(report.new_product_patterns))
    finally:
        await engine.close()
