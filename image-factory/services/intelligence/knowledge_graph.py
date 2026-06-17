from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.models import KnowledgeNode, KnowledgeEdge, IntelligenceEventType
from services.intelligence.event_emitter import EventEmitter

logger = get_logger(__name__)

NODE_KEY_PREFIX = "intel:kg:node:"
EDGE_INDEX_PREFIX = "intel:kg:edge:"
NODE_TYPE_INDEX_PREFIX = "intel:kg:type:"
NODE_MARKETPLACE_INDEX = "intel:kg:marketplace:"
EDGE_KEY_PREFIX = "intel:kg:edge_data:"


class ProductKnowledgeGraph:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self._redis: aioredis.Redis | None = None
        self.emitter = emitter or EventEmitter()
        self._local_nodes: dict[str, KnowledgeNode] = {}
        self._local_edges: list[KnowledgeEdge] = []

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        return self._redis

    async def add_product(
        self,
        name: str,
        marketplace: str,
        url: str,
        attributes: dict[str, Any] | None = None,
        image_hashes: list[str] | None = None,
    ) -> KnowledgeNode:
        node = KnowledgeNode(
            id=str(uuid.uuid4()),
            type="product",
            name=name,
            marketplace=marketplace,
            url=url,
            attributes=attributes or {},
            image_hashes=image_hashes or [],
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        await self._save_node(node)
        await self._index_node(node)
        await self.emitter.emit(IntelligenceEventType.KNOWLEDGE_NODE_CREATED, marketplace, {
            "node_id": node.id,
            "node_type": "product",
            "name": name,
        })
        return node

    async def add_supplier(
        self,
        name: str,
        marketplace: str,
        url: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> KnowledgeNode:
        node = KnowledgeNode(
            id=str(uuid.uuid4()),
            type="supplier",
            name=name,
            marketplace=marketplace,
            url=url,
            attributes=attributes or {},
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        await self._save_node(node)
        await self._index_node(node)
        return node

    async def add_category(
        self,
        name: str,
        marketplace: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> KnowledgeNode:
        node = KnowledgeNode(
            id=str(uuid.uuid4()),
            type="category",
            name=name,
            marketplace=marketplace,
            attributes=attributes or {},
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        await self._save_node(node)
        await self._index_node(node)
        return node

    async def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        weight: float = 1.0,
    ) -> KnowledgeEdge:
        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            weight=weight,
            discovered_at=datetime.utcnow().isoformat(),
        )
        await self._save_edge(edge)
        await self.emitter.emit(IntelligenceEventType.KNOWLEDGE_EDGE_CREATED, "", {
            "source_id": source_id,
            "target_id": target_id,
            "relationship": relationship,
            "weight": weight,
        })
        return edge

    async def link_product_to_supplier(self, product_id: str, supplier_id: str, weight: float = 1.0) -> KnowledgeEdge:
        return await self.add_relationship(product_id, supplier_id, "supplied_by", weight)

    async def link_similar_products(self, product_id_a: str, product_id_b: str, similarity: float = 1.0) -> KnowledgeEdge:
        return await self.add_relationship(product_id_a, product_id_b, "similar_to", similarity)

    async def link_product_to_category(self, product_id: str, category_id: str) -> KnowledgeEdge:
        return await self.add_relationship(product_id, category_id, "belongs_to")

    async def _save_node(self, node: KnowledgeNode) -> None:
        redis_conn = await self._get_redis()
        key = f"{NODE_KEY_PREFIX}{node.id}"
        await redis_conn.set(key, json.dumps(node.to_dict()), ex=86400 * 90)
        self._local_nodes[node.id] = node

    async def _index_node(self, node: KnowledgeNode) -> None:
        redis_conn = await self._get_redis()
        pipe = redis_conn.pipeline()
        pipe.sadd(f"{NODE_TYPE_INDEX_PREFIX}{node.type}", node.id)
        pipe.expire(f"{NODE_TYPE_INDEX_PREFIX}{node.type}", 86400 * 90)
        if node.marketplace:
            pipe.sadd(f"{NODE_MARKETPLACE_INDEX}{node.marketplace}", node.id)
            pipe.expire(f"{NODE_MARKETPLACE_INDEX}{node.marketplace}", 86400 * 90)
        await pipe.execute()

    async def _save_edge(self, edge: KnowledgeEdge) -> None:
        redis_conn = await self._get_redis()
        source_key = f"{EDGE_INDEX_PREFIX}{edge.source_id}"
        target_key = f"{EDGE_INDEX_PREFIX}{edge.target_id}"
        pipe = redis_conn.pipeline()
        edge_data = json.dumps(edge.to_dict())
        edge_key = f"{EDGE_KEY_PREFIX}{edge.source_id}:{edge.target_id}:{edge.relationship}"
        pipe.set(edge_key, edge_data, ex=86400 * 90)
        pipe.sadd(source_key, f"{edge.target_id}:{edge.relationship}")
        pipe.sadd(target_key, f"{edge.source_id}:{edge.relationship}")
        pipe.expire(source_key, 86400 * 90)
        pipe.expire(target_key, 86400 * 90)
        await pipe.execute()
        self._local_edges.append(edge)

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        if node_id in self._local_nodes:
            return self._local_nodes[node_id]
        redis_conn = await self._get_redis()
        key = f"{NODE_KEY_PREFIX}{node_id}"
        data = await redis_conn.get(key)
        if data:
            try:
                node = KnowledgeNode(**json.loads(data))
                self._local_nodes[node_id] = node
                return node
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("node_deserialize_failed", node_id=node_id, error=str(exc))
        return None

    async def get_nodes_by_type(self, node_type: str) -> list[KnowledgeNode]:
        redis_conn = await self._get_redis()
        index_key = f"{NODE_TYPE_INDEX_PREFIX}{node_type}"
        node_ids = await redis_conn.smembers(index_key)
        nodes: list[KnowledgeNode] = []
        for nid in node_ids:
            nid_str = nid.decode() if isinstance(nid, bytes) else nid
            node = await self.get_node(nid_str)
            if node:
                nodes.append(node)
        return nodes

    async def get_nodes_by_marketplace(self, marketplace: str) -> list[KnowledgeNode]:
        redis_conn = await self._get_redis()
        index_key = f"{NODE_MARKETPLACE_INDEX}{marketplace}"
        node_ids = await redis_conn.smembers(index_key)
        nodes: list[KnowledgeNode] = []
        for nid in node_ids:
            nid_str = nid.decode() if isinstance(nid, bytes) else nid
            node = await self.get_node(nid_str)
            if node:
                nodes.append(node)
        return nodes

    async def get_related_nodes(self, node_id: str) -> list[tuple[KnowledgeNode, str, float]]:
        redis_conn = await self._get_redis()
        index_key = f"{EDGE_INDEX_PREFIX}{node_id}"
        edges = await redis_conn.smembers(index_key)
        results: list[tuple[KnowledgeNode, str, float]] = []
        for edge_entry in edges:
            edge_str = edge_entry.decode() if isinstance(edge_entry, bytes) else edge_entry
            parts = edge_str.split(":", 1)
            if len(parts) != 2:
                continue
            related_id, relationship = parts
            node = await self.get_node(related_id)
            if node:
                edge_key = f"{EDGE_KEY_PREFIX}{node_id}:{related_id}:{relationship}"
                edge_data = await redis_conn.get(edge_key)
                weight = 1.0
                if edge_data:
                    try:
                        weight = json.loads(edge_data).get("weight", 1.0)
                    except json.JSONDecodeError:
                        pass
                results.append((node, relationship, weight))
        return results

    async def find_supplier_products(self, supplier_id: str) -> list[KnowledgeNode]:
        related = await self.get_related_nodes(supplier_id)
        return [node for node, rel, _ in related if rel == "supplied_by"]

    async def find_similar_products(self, product_id: str) -> list[tuple[KnowledgeNode, float]]:
        related = await self.get_related_nodes(product_id)
        return [(node, weight) for node, rel, weight in related if rel == "similar_to"]

    async def cross_marketplace_matching(self, product_name: str) -> list[KnowledgeNode]:
        redis_conn = await self._get_redis()
        all_product_ids = await redis_conn.smembers(f"{NODE_TYPE_INDEX_PREFIX}product")
        matches: list[KnowledgeNode] = []
        name_lower = product_name.lower()
        for pid in all_product_ids:
            pid_str = pid.decode() if isinstance(pid, bytes) else pid
            node = await self.get_node(pid_str)
            if node and name_lower in node.name.lower():
                matches.append(node)
        return matches

    async def get_stats(self) -> dict[str, Any]:
        redis_conn = await self._get_redis()
        product_count = await redis_conn.scard(f"{NODE_TYPE_INDEX_PREFIX}product")
        supplier_count = await redis_conn.scard(f"{NODE_TYPE_INDEX_PREFIX}supplier")
        category_count = await redis_conn.scard(f"{NODE_TYPE_INDEX_PREFIX}category")
        edge_keys = await redis_conn.keys(f"{EDGE_KEY_PREFIX}*")
        return {
            "products": int(product_count),
            "suppliers": int(supplier_count),
            "categories": int(category_count),
            "relationships": len(edge_keys),
            "local_nodes_cached": len(self._local_nodes),
            "local_edges_cached": len(self._local_edges),
        }

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
