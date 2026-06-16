from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CreditEstimate:
    total_products: int
    total_images: int
    estimated_cost_cents: float
    claude_calls: int
    nano_banana_calls: int
    cost_per_image_cents: float = 1.0
    cost_per_claude_call_cents: float = 0.03


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

    COST_PER_IMAGE_CENTS = 1.0
    COST_PER_CLAUDE_CALL_CENTS = 0.03
    LOW_CREDIT_THRESHOLD_CENTS = 50.0
    CRITICAL_CREDIT_THRESHOLD_CENTS = 10.0

    def __init__(self) -> None:
        self._cached_balance: Optional[float] = None

    async def check_balance(self) -> float:
        if self._cached_balance is not None:
            return self._cached_balance
        try:
            from services.nano_banana.client import NanoBananaClient
            provider = NanoBananaClient()
            try:
                health = await provider.check_health()
            finally:
                await provider.close()
            max_cents = settings.smoke_max_cost_cents if settings.smoke_test_mode else 5000.0
            self._cached_balance = max_cents
            return self._cached_balance
        except Exception as e:
            logger.warning("credit_balance_check_failed", error=str(e))
            return 5000.0

    def invalidate_cache(self) -> None:
        self._cached_balance = None

    def estimate_cost(self, product_count: int, images_per_product: int = 1, use_claude: bool = True) -> CreditEstimate:
        total_images = product_count * images_per_product
        claude_calls = product_count if use_claude else 0
        nano_banana_calls = total_images

        estimated_cost = (
            claude_calls * self.COST_PER_CLAUDE_CALL_CENTS
            + nano_banana_calls * self.COST_PER_IMAGE_CENTS
        )

        return CreditEstimate(
            total_products=product_count,
            total_images=total_images,
            estimated_cost_cents=estimated_cost,
            claude_calls=claude_calls,
            nano_banana_calls=nano_banana_calls,
            cost_per_image_cents=self.COST_PER_IMAGE_CENTS,
            cost_per_claude_call_cents=self.COST_PER_CLAUDE_CALL_CENTS,
        )

    async def check_sufficient_credits(self, product_count: int, images_per_product: int = 1, use_claude: bool = True) -> CreditStatus:
        balance = await self.check_balance()
        estimate = self.estimate_cost(product_count, images_per_product, use_claude)

        deficit = estimate.estimated_cost_cents - balance
        max_affordable = int(balance / (self.COST_PER_IMAGE_CENTS + (self.COST_PER_CLAUDE_CALL_CENTS if use_claude else 0))) if balance > 0 else 0
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
