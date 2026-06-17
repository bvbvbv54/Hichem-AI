from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.knowledge_graph import ProductKnowledgeGraph
from services.intelligence.models import KnowledgeNode

logger = get_logger(__name__)

EMBEDDING_PREFIX = "intel:embedding:"
EMBEDDING_INDEX_PREFIX = "intel:embedding_index:"


class VectorSearch:
    def __init__(self, knowledge_graph: ProductKnowledgeGraph | None = None) -> None:
        self._redis: aioredis.Redis | None = None
        self.knowledge_graph = knowledge_graph or ProductKnowledgeGraph()

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def generate_embedding(self, text: str) -> list[float]:
        try:
            from configs.settings import settings as app_settings
            if app_settings.gemini_api_key:
                import google.generativeai as genai
                genai.configure(api_key=app_settings.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                result = model.generate_content(f"Generate a semantic embedding vector representation of: {text[:500]}")
                if result and result.text:
                    import re
                    numbers = re.findall(r"-?\d+\.?\d*", result.text)
                    if len(numbers) >= 128:
                        return [float(n) for n in numbers[:256]]
            if app_settings.claude_api_key:
                from services.claude.client import ClaudeClient
                client = ClaudeClient()
                response = await client.generate(
                    f"Return a list of 128 floating point numbers representing a semantic embedding for: {text[:300]}",
                    max_tokens=1024,
                )
                if response:
                    import re
                    numbers = re.findall(r"-?\d+\.?\d*", response)
                    if len(numbers) >= 128:
                        return [float(n) for n in numbers[:256]]
        except Exception as exc:
            logger.warning("embedding_generation_failed", error=str(exc))

        import hashlib
        seed = hashlib.sha256(text.encode()).digest()
        import random
        rng = random.Random(seed)
        return [rng.gauss(0, 0.1) for _ in range(128)]

    async def store_embedding(self, node_id: str, embedding: list[float]) -> None:
        redis_conn = await self._get_redis()
        key = f"{EMBEDDING_PREFIX}{node_id}"
        await redis_conn.set(key, json.dumps(embedding), ex=86400 * 90)

    async def get_embedding(self, node_id: str) -> list[float] | None:
        redis_conn = await self._get_redis()
        key = f"{EMBEDDING_PREFIX}{node_id}"
        data = await redis_conn.get(key)
        if data:
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def find_similar(
        self,
        query_embedding: list[float],
        node_type: str = "product",
        limit: int = 20,
        threshold: float = 0.5,
    ) -> list[tuple[KnowledgeNode, float]]:
        nodes = await self.knowledge_graph.get_nodes_by_type(node_type)
        scored: list[tuple[KnowledgeNode, float]] = []
        for node in nodes:
            node_emb = await self.get_embedding(node.id)
            if node_emb:
                sim = self._cosine_similarity(query_embedding, node_emb)
                if sim >= threshold:
                    scored.append((node, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def find_similar_products(
        self,
        product_id: str,
        limit: int = 10,
    ) -> list[tuple[KnowledgeNode, float]]:
        embedding = await self.get_embedding(product_id)
        if not embedding:
            return []
        return await self.find_similar(embedding, "product", limit)

    async def cross_marketplace_matching(
        self,
        query_embedding: list[float],
        marketplace: str = "",
        limit: int = 10,
    ) -> list[tuple[KnowledgeNode, float]]:
        nodes = await self.knowledge_graph.get_nodes_by_type("product")
        if marketplace:
            nodes = [n for n in nodes if n.marketplace != marketplace]
        scored: list[tuple[KnowledgeNode, float]] = []
        for node in nodes:
            node_emb = await self.get_embedding(node.id)
            if node_emb:
                sim = self._cosine_similarity(query_embedding, node_emb)
                if sim >= 0.6:
                    scored.append((node, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def duplicate_detection(
        self,
        query_embedding: list[float],
        threshold: float = 0.9,
    ) -> list[tuple[KnowledgeNode, float]]:
        return await self.find_similar(query_embedding, "product", limit=5, threshold=threshold)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
