from __future__ import annotations

import httpx
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from configs.settings import settings
from configs.logging import get_logger
from database.models.asset import Asset
from services.settings_service import get_provider_api_key, get_setting

logger = get_logger(__name__)


@dataclass
class CreditEstimate:
    total_products: int
    total_images: int
    estimated_cost_cents: float
    nano_banana_calls: int
    cost_per_image_cents: float = 1.0


@dataclass
class CreditStatus:
    sufficient: bool
    estimated_cost_cents: float
    available_credits_cents: float
    deficit_cents: float
    total_images_requested: int
    max_images_affordable: int
    warning_message: str = ""


class NanoBananaCreditBalancer:

    LOW_CREDIT_THRESHOLD_CENTS = 50.0
    CRITICAL_CREDIT_THRESHOLD_CENTS = 10.0

    def __init__(self) -> None:
        self._cached_key_valid: Optional[bool] = None
        self._cached_models: Optional[list[str]] = None
        self._cost_per_image_cents: float = 1.0

    async def _load_pricing(self, session: Optional[AsyncSession] = None) -> None:
        if session:
            img_cost = await get_setting("cost_per_image_cents", session, "1.0")
            self._cost_per_image_cents = float(img_cost)
        else:
            self._cost_per_image_cents = 1.0

    @property
    def COST_PER_IMAGE_CENTS(self) -> float:
        return self._cost_per_image_cents

    async def validate_api_key(self, session: Optional[AsyncSession] = None) -> dict:
        api_key = ""
        if session:
            from services.settings_service import get_google_api_key
            api_key, _ = await get_google_api_key(session)
        if not api_key:
            return {"valid": False, "error": "No Google API key configured. Set one in Settings.", "models": []}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"].replace("models/", "") for m in data.get("models", [])]
                    self._cached_key_valid = True
                    self._cached_models = models
                    return {"valid": True, "models": models}
                elif resp.status_code == 403:
                    return {"valid": False, "error": "API key invalid or unauthorized", "models": []}
                else:
                    return {"valid": False, "error": f"API returned HTTP {resp.status_code}", "models": []}
        except Exception as e:
            logger.warning("api_key_validation_failed", error=str(e))
            return {"valid": False, "error": str(e), "models": []}

    async def get_total_usage_cents(self, session: AsyncSession) -> float:
        await self._load_pricing(session)
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        result = await session.execute(
            select(func.count(Asset.id)).where(
                and_(
                    Asset.created_at >= month_start,
                    Asset.created_at < month_end,
                    text("meta->>'provider' = 'replicate'"),
                )
            )
        )
        total_images = result.scalar() or 0
        return total_images * self._cost_per_image_cents

    async def check_balance(self, session: Optional[AsyncSession] = None) -> float:
        await self._load_pricing(session)
        budget_cents = float(settings.monthly_budget_cents)
        if session:
            db_budget = await get_setting("monthly_budget_cents", session, "")
            if db_budget:
                budget_cents = float(db_budget)
            usage_cents = await self.get_total_usage_cents(session)
            remaining = max(0.0, budget_cents - usage_cents)
        else:
            remaining = budget_cents
        return remaining

    def invalidate_cache(self) -> None:
        self._cached_key_valid = None
        self._cached_models = None

    def estimate_cost(self, product_count: int, images_per_product: int = 1) -> CreditEstimate:
        total_images = product_count * images_per_product
        nano_banana_calls = total_images
        estimated_cost = nano_banana_calls * self._cost_per_image_cents

        return CreditEstimate(
            total_products=product_count,
            total_images=total_images,
            estimated_cost_cents=estimated_cost,
            nano_banana_calls=nano_banana_calls,
            cost_per_image_cents=self._cost_per_image_cents,
        )

    async def check_sufficient_credits(self, session: AsyncSession, product_count: int, images_per_product: int = 1) -> CreditStatus:
        balance = await self.check_balance(session)
        estimate = self.estimate_cost(product_count, images_per_product)

        deficit = estimate.estimated_cost_cents - balance
        max_affordable = int(balance / self._cost_per_image_cents) if balance > 0 else 0
        images_per_product_effective = max(1, images_per_product)
        max_products_affordable = max(0, max_affordable // images_per_product_effective)

        warning = ""
        if deficit > 0:
            warning = (
                f"Insufficient credits! Estimated cost ${estimate.estimated_cost_cents/100:.2f} "
                f"exceeds available balance ${balance/100:.2f} by ${deficit/100:.2f}. "
                f"Can afford ~{max_products_affordable} products ({max_affordable} images)."
            )
        elif balance < self.LOW_CREDIT_THRESHOLD_CENTS:
            warning = (
                f"Low credits warning: Only ${balance/100:.2f} remaining. "
                f"Estimated cost for this batch: ${estimate.estimated_cost_cents/100:.2f}. "
                f"This will consume most of your remaining credits."
            )

        return CreditStatus(
            sufficient=deficit <= 0,
            estimated_cost_cents=estimate.estimated_cost_cents,
            available_credits_cents=balance,
            deficit_cents=max(0, deficit),
            total_images_requested=estimate.total_images,
            max_images_affordable=max_affordable,
            warning_message=warning,
        )


_balancer: Optional[NanoBananaCreditBalancer] = None


def get_credit_balancer() -> NanoBananaCreditBalancer:
    global _balancer
    if _balancer is None:
        _balancer = NanoBananaCreditBalancer()
    return _balancer
