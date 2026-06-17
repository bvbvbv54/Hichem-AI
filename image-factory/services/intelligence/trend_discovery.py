from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from configs.logging import get_logger
from configs.settings import settings
from services.intelligence.knowledge_graph import ProductKnowledgeGraph
from services.intelligence.models import TrendReport, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

TREND_REPORT_PREFIX = "intel:trend:"


class TrendDiscoveryEngine:
    def __init__(
        self,
        knowledge_graph: ProductKnowledgeGraph | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.knowledge_graph = knowledge_graph or ProductKnowledgeGraph()
        self.emitter = emitter or EventEmitter()

    async def generate_daily_report(self) -> TrendReport:
        report = TrendReport(
            report_type="daily",
            period=(datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            generated_at=datetime.utcnow().isoformat(),
        )
        products = await self.knowledge_graph.get_nodes_by_type("product")

        category_counts: Counter[str] = Counter()
        keyword_counts: Counter[str] = Counter()
        marketplace_sets: dict[str, set[str]] = defaultdict(set)
        supplier_seen: set[str] = set()

        for product in products:
            cat = product.attributes.get("category", "")
            if cat:
                category_counts[cat] += 1
            name = product.name.lower()
            words = [w for w in name.split() if len(w) > 2]
            keyword_counts.update(words)
            if product.marketplace:
                marketplace_sets[product.marketplace].add(product.name)

        report.fast_growing_categories = [
            {"category": cat, "count": count}
            for cat, count in category_counts.most_common(10)
        ]
        report.repeated_keywords = [
            {"keyword": kw, "count": count}
            for kw, count in keyword_counts.most_common(20)
        ]
        report.cross_marketplace_products = [
            {"product": name, "marketplaces": list(mps)}
            for name, mps in marketplace_sets.items()
            if len(mps) > 1
        ][:20]

        await self._save_report(report)
        await self.emitter.emit(IntelligenceEventType.TREND_REPORT_GENERATED, "all", {
            "report_type": "daily",
            "period": report.period,
        })
        logger.info("daily_trend_report_generated", categories=len(report.fast_growing_categories))
        return report

    async def generate_weekly_report(self) -> TrendReport:
        report = TrendReport(
            report_type="weekly",
            period=(datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
            generated_at=datetime.utcnow().isoformat(),
        )
        products = await self.knowledge_graph.get_nodes_by_type("product")

        category_counts: Counter[str] = Counter()
        marketplace_counts: Counter[str] = Counter()
        cross_mp: dict[str, set[str]] = defaultdict(set)

        for product in products:
            cat = product.attributes.get("category", "")
            if cat:
                category_counts[cat] += 1
            if product.marketplace:
                marketplace_counts[product.marketplace] += 1
                cross_mp[product.name].add(product.marketplace)

        report.fast_growing_categories = [
            {"category": cat, "count": count}
            for cat, count in category_counts.most_common(15)
        ]
        report.cross_marketplace_products = [
            {"product": name, "marketplaces": list(mps)}
            for name, mps in cross_mp.items() if len(mps) > 1
        ][:30]
        report.marketplace_opportunities = [
            {"marketplace": mp, "product_count": count}
            for mp, count in marketplace_counts.most_common()
        ]

        await self._save_report(report)
        await self.emitter.emit(IntelligenceEventType.TREND_REPORT_GENERATED, "all", {
            "report_type": "weekly",
            "period": report.period,
        })
        logger.info("weekly_trend_report_generated")
        return report

    async def generate_marketplace_opportunity_report(self) -> TrendReport:
        report = TrendReport(
            report_type="opportunity",
            period="all",
            generated_at=datetime.utcnow().isoformat(),
        )
        products = await self.knowledge_graph.get_nodes_by_type("product")

        marketplace_products: dict[str, list[KnowledgeNode]] = defaultdict(list)
        for p in products:
            if p.marketplace:
                marketplace_products[p.marketplace].append(p)

        for mp, mps in marketplace_products.items():
            cat_counts: Counter[str] = Counter()
            for p in mps:
                cat = p.attributes.get("category", "")
                if cat:
                    cat_counts[cat] += 1
            report.new_product_patterns.append({
                "marketplace": mp,
                "product_count": len(mps),
                "top_categories": [{"category": c, "count": cnt} for c, cnt in cat_counts.most_common(5)],
            })

        report.marketplace_opportunities = [
            {"marketplace": mp, "product_count": len(products), "potential": "high" if len(products) < 100 else "established"}
            for mp, products in marketplace_products.items()
        ]

        await self._save_report(report)
        return report

    async def _save_report(self, report: TrendReport) -> None:
        import redis.asyncio as aioredis
        redis_conn = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            key = f"{TREND_REPORT_PREFIX}{report.report_type}:{report.period}"
            await redis_conn.set(key, json.dumps(report.to_dict()), ex=86400 * 90)
        finally:
            await redis_conn.aclose()

    async def get_latest_report(self, report_type: str = "daily") -> TrendReport | None:
        import redis.asyncio as aioredis
        redis_conn = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            keys = await redis_conn.keys(f"{TREND_REPORT_PREFIX}{report_type}:*")
            if not keys:
                return None
            latest_key = sorted(keys, reverse=True)[0]
            k = latest_key.decode() if isinstance(latest_key, bytes) else latest_key
            data = await redis_conn.get(k)
            if data:
                return TrendReport(**json.loads(data))
        finally:
            await redis_conn.aclose()
        return None

    async def close(self) -> None:
        await self.knowledge_graph.close()
