from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ChallengeType(str, Enum):
    CAPTCHA = "captcha"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    CLOUDFLARE_JS = "cloudflare_js"
    CLOUDFLARE_TURNSTILE = "cloudflare_turnstile"
    LOGIN_CHALLENGE = "login_challenge"
    RATE_LIMIT = "rate_limit"
    IP_BLOCK = "ip_block"
    UNKNOWN = "unknown"


class ExtractionMethod(str, Enum):
    JSON_LD = "json_ld"
    EMBEDDED_JSON = "embedded_json"
    INTERNAL_API = "internal_api"
    STATIC_HTML = "static_html"
    BROWSER_AUTOMATION = "browser_automation"
    AI_EXTRACTION = "ai_extraction"


@dataclass
class MarketplaceSession:
    id: str
    marketplace: str
    cookies: dict[str, str] = field(default_factory=dict)
    local_storage: dict[str, str] = field(default_factory=dict)
    session_age: float = 0.0
    request_count: int = 0
    captcha_count: int = 0
    trust_score: float = 0.0
    last_success: str = ""
    last_failure: str = ""
    last_used: str = ""
    browser_context_id: str = ""
    user_agent: str = ""
    created_at: str = ""
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "marketplace": self.marketplace,
            "cookies": self.cookies,
            "local_storage": self.local_storage,
            "session_age": self.session_age,
            "request_count": self.request_count,
            "captcha_count": self.captcha_count,
            "trust_score": self.trust_score,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "last_used": self.last_used,
            "browser_context_id": self.browser_context_id,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceSession:
        return cls(**data)


@dataclass
class CaptchaEvent:
    id: str
    domain: str
    timestamp: str
    session_id: str
    url: str
    challenge_type: ChallengeType
    html_signature: str
    marketplace: str = ""
    resolved: bool = False
    resolution_method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "url": self.url,
            "challenge_type": self.challenge_type.value,
            "html_signature": self.html_signature,
            "marketplace": self.marketplace,
            "resolved": self.resolved,
            "resolution_method": self.resolution_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptchaEvent:
        data["challenge_type"] = ChallengeType(data.get("challenge_type", "unknown"))
        return cls(**data)


@dataclass
class MarketplaceHealth:
    marketplace: str
    period_start: str
    period_end: str
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    captcha_count: int = 0
    blocked_count: int = 0
    avg_extraction_time_ms: float = 0.0
    success_rate: float = 0.0
    captcha_rate: float = 0.0
    session_count: int = 0
    healthy_session_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "captcha_count": self.captcha_count,
            "blocked_count": self.blocked_count,
            "avg_extraction_time_ms": self.avg_extraction_time_ms,
            "success_rate": self.success_rate,
            "captcha_rate": self.captcha_rate,
            "session_count": self.session_count,
            "healthy_session_count": self.healthy_session_count,
        }


@dataclass
class ExtractionAttempt:
    method: ExtractionMethod
    success: bool
    duration_ms: float
    marketplace: str
    url: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method.value,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "marketplace": self.marketplace,
            "url": self.url,
            "error": self.error,
        }


@dataclass
class MarketplaceProfile:
    domain: str
    name: str
    selectors: dict[str, str] = field(default_factory=dict)
    json_paths: dict[str, str] = field(default_factory=dict)
    api_endpoints: list[str] = field(default_factory=list)
    successful_patterns: list[dict[str, Any]] = field(default_factory=list)
    captcha_signatures: list[str] = field(default_factory=list)
    redirect_patterns: list[str] = field(default_factory=list)
    session_rules: dict[str, Any] = field(default_factory=dict)
    preferred_extraction_method: str = ""
    extraction_success_rates: dict[str, float] = field(default_factory=dict)
    request_rules: dict[str, Any] = field(default_factory=dict)
    image_patterns: dict[str, str] = field(default_factory=dict)
    last_updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "name": self.name,
            "selectors": self.selectors,
            "json_paths": self.json_paths,
            "api_endpoints": self.api_endpoints,
            "successful_patterns": self.successful_patterns,
            "captcha_signatures": self.captcha_signatures,
            "redirect_patterns": self.redirect_patterns,
            "session_rules": self.session_rules,
            "preferred_extraction_method": self.preferred_extraction_method,
            "extraction_success_rates": self.extraction_success_rates,
            "request_rules": self.request_rules,
            "image_patterns": self.image_patterns,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceProfile:
        return cls(**data)


@dataclass
class KnowledgeNode:
    id: str
    type: str
    name: str
    marketplace: str = ""
    url: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    image_hashes: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "marketplace": self.marketplace,
            "url": self.url,
            "attributes": self.attributes,
            "image_hashes": self.image_hashes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeEdge:
    source_id: str
    target_id: str
    relationship: str
    weight: float = 1.0
    discovered_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
            "weight": self.weight,
            "discovered_at": self.discovered_at,
        }


@dataclass
class TrendReport:
    report_type: str
    period: str
    generated_at: str
    fast_growing_categories: list[dict[str, Any]] = field(default_factory=list)
    repeated_keywords: list[dict[str, Any]] = field(default_factory=list)
    cross_marketplace_products: list[dict[str, Any]] = field(default_factory=list)
    new_suppliers: list[dict[str, Any]] = field(default_factory=list)
    new_product_patterns: list[dict[str, Any]] = field(default_factory=list)
    marketplace_opportunities: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "period": self.period,
            "generated_at": self.generated_at,
            "fast_growing_categories": self.fast_growing_categories,
            "repeated_keywords": self.repeated_keywords,
            "cross_marketplace_products": self.cross_marketplace_products,
            "new_suppliers": self.new_suppliers,
            "new_product_patterns": self.new_product_patterns,
            "marketplace_opportunities": self.marketplace_opportunities,
        }


class IntelligenceEventType(str, Enum):
    SESSION_CREATED = "session_created"
    SESSION_REUSED = "session_reused"
    SESSION_ROTATED = "session_rotated"
    SESSION_EXPIRED = "session_expired"
    CAPTCHA_DETECTED = "captcha_detected"
    CAPTCHA_RESOLVED = "captcha_resolved"
    TRUST_SCORE_CHANGED = "trust_score_changed"
    PRODUCT_EXTRACTED = "product_extracted"
    MARKETPLACE_BLOCKED = "marketplace_blocked"
    STRATEGY_SELECTED = "strategy_selected"
    STRATEGY_FAILED = "strategy_failed"
    IMAGE_DOWNLOADED = "image_downloaded"
    MARKETPLACE_PROFILE_UPDATED = "marketplace_profile_updated"
    NEW_DOMAIN_DISCOVERED = "new_domain_discovered"
    KNOWLEDGE_NODE_CREATED = "knowledge_node_created"
    KNOWLEDGE_EDGE_CREATED = "knowledge_edge_created"
    TREND_REPORT_GENERATED = "trend_report_generated"
    HEALTH_ALERT = "health_alert"
    BROWSER_CONTEXT_CREATED = "browser_context_created"
    BROWSER_CONTEXT_REUSED = "browser_context_reused"
    REQUEST_DELAYED = "request_delayed"
    BURST_DETECTED = "burst_detected"


@dataclass
class IntelligenceEvent:
    event_type: IntelligenceEventType
    marketplace: str
    timestamp: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type.value,
            "marketplace": self.marketplace,
            "timestamp": self.timestamp,
            "data": self.data,
        }
