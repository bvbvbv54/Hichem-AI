from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from configs.logging import get_logger
from services.intelligence.session_manager import SessionManager
from services.intelligence.captcha_manager import CaptchaManager
from services.intelligence.marketplace_health import MarketplaceHealthMonitor
from services.intelligence.request_engine import AdaptiveRequestEngine
from services.intelligence.extraction_strategy import ExtractionStrategyHierarchy
from services.intelligence.profile_manager import MarketplaceProfileManager
from services.intelligence.domain_discovery import DomainDiscoverer
from services.intelligence.knowledge_graph import ProductKnowledgeGraph
from services.intelligence.browser_pool import BrowserPool
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)


class IntelligenceOrchestrator:
    def __init__(self) -> None:
        self.emitter = EventEmitter()
        self.session_manager = SessionManager(emitter=self.emitter)
        self.captcha_manager = CaptchaManager(emitter=self.emitter)
        self.health_monitor = MarketplaceHealthMonitor(emitter=self.emitter)
        self.request_engine = AdaptiveRequestEngine(emitter=self.emitter)
        self.profile_manager = MarketplaceProfileManager(emitter=self.emitter)
        self.domain_discoverer = DomainDiscoverer(profile_manager=self.profile_manager, emitter=self.emitter)
        self.extraction_strategy = ExtractionStrategyHierarchy(
            profile_manager=self.profile_manager,
            request_engine=self.request_engine,
            emitter=self.emitter,
        )
        self.knowledge_graph = ProductKnowledgeGraph(emitter=self.emitter)
        self.browser_pool = BrowserPool(emitter=self.emitter)

    def get_domain(self, url: str) -> str:
        return urlparse(url).netloc.replace("www.", "")

    async def prepare_request(self, url: str) -> tuple[str, str, dict[str, Any]]:
        domain = self.get_domain(url)
        marketplace = domain

        session = await self.session_manager.get_or_create_session(marketplace)
        rules = self.request_engine.get_rules(domain)
        delay = await self.request_engine.acquire(domain)
        profile = await self.profile_manager.get_profile(domain)

        return domain, marketplace, {
            "session": session,
            "rules": rules,
            "delay": delay,
            "profile": profile,
        }

    async def record_success(
        self,
        url: str,
        extracted: bool = True,
        images_downloaded: bool = False,
        duration_ms: float = 0,
    ) -> None:
        domain = self.get_domain(url)
        self.request_engine.release(domain)
        await self.request_engine.record_success(domain)
        await self.health_monitor.record_extraction(domain, True, duration_ms)

    async def record_failure(
        self,
        url: str,
        failure_type: str = "unknown",
        was_captcha: bool = False,
        was_blocked: bool = False,
        duration_ms: float = 0,
        html: str = "",
        session_id: str = "",
    ) -> None:
        domain = self.get_domain(url)
        self.request_engine.release(domain)
        await self.request_engine.record_failure(domain)
        await self.health_monitor.record_extraction(domain, False, duration_ms, was_captcha, was_blocked)

        if was_captcha and html and session_id:
            from services.intelligence.models import ChallengeType
            await self.captcha_manager.record_event(
                domain=domain,
                session_id=session_id,
                url=url,
                challenge_type=ChallengeType.CAPTCHA,
                html=html,
                marketplace=domain,
            )

    async def discover_marketplace(self, url: str, html: str) -> Any:
        domain = self.get_domain(url)
        profile = await self.profile_manager.get_profile(domain)
        if profile:
            return profile
        return await self.domain_discoverer.analyze_domain(url, html, domain)

    async def extract_product(self, url: str, html: str | None = None, marketplace: str = "") -> tuple[Any, Any]:
        return await self.extraction_strategy.extract(url, html, marketplace)

    async def add_to_knowledge_graph(
        self,
        name: str,
        marketplace: str,
        url: str,
        attributes: dict[str, Any] | None = None,
        image_hashes: list[str] | None = None,
    ) -> Any:
        return await self.knowledge_graph.add_product(name, marketplace, url, attributes, image_hashes)

    async def get_marketplace_health(self, marketplace: str) -> Any:
        return await self.health_monitor.get_current_health(marketplace)

    async def get_session_pool_stats(self, marketplace: str) -> Any:
        return await self.session_manager.get_pool_stats(marketplace)

    async def close(self) -> None:
        await self.session_manager.close()
        await self.captcha_manager.close()
        await self.health_monitor.close()
        await self.profile_manager.close()
        await self.knowledge_graph.close()
        await self.browser_pool.close()
        await self.emitter.close()
