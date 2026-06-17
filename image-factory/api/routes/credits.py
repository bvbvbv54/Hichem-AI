from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from configs.logging import get_logger
from configs.settings import settings
from services.nano_banana.credit_balancer import get_credit_balancer
from services.settings_service import get_provider_api_key, get_setting_with_source

logger = get_logger(__name__)

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/status")
async def credit_status(session: AsyncSession = Depends(get_session)):
    balancer = get_credit_balancer()
    key_validation = await balancer.validate_api_key(session)
    balance = await balancer.check_balance(session)
    used = await balancer.get_total_usage_cents(session)
    estimate = balancer.estimate_cost(product_count=1, images_per_product=1, use_claude=True)

    key_val, key_src = await get_setting_with_source("nano_banana_api_key", session)
    budget_val, budget_src = await get_setting_with_source("monthly_budget_cents", session)
    budget_cents = int(budget_val) if budget_val else settings.monthly_budget_cents

    return {
        "api_key_configured": bool(key_val),
        "api_key_source": key_src,
        "api_key_valid": key_validation.get("valid", False),
        "key_check_error": key_validation.get("error"),
        "available_models": key_validation.get("models", []),
        "available_credits_cents": balance,
        "available_credits_dollars": round(balance / 100, 2),
        "used_credits_cents": used,
        "used_credits_dollars": round(used / 100, 2),
        "monthly_budget_cents": budget_cents,
        "monthly_budget_dollars": round(budget_cents / 100, 2),
        "budget_source": budget_src,
        "cost_per_image_cents": estimate.cost_per_image_cents,
        "cost_per_claude_call_cents": estimate.cost_per_claude_call_cents,
        "estimated_cost_per_product_cents": estimate.estimated_cost_cents,
        "estimated_cost_per_product_dollars": round(estimate.estimated_cost_cents / 100, 4),
        "smoke_test_mode": settings.smoke_test_mode,
    }


@router.get("/estimate")
async def credit_estimate(
    products: int = 1,
    images_per_product: int = 1,
    use_claude: bool = True,
    session: AsyncSession = Depends(get_session),
):
    balancer = get_credit_balancer()
    status = await balancer.check_sufficient_credits(session, products, images_per_product, use_claude)
    return {
        "sufficient": status.sufficient,
        "estimated_cost_cents": status.estimated_cost_cents,
        "estimated_cost_dollars": round(status.estimated_cost_cents / 100, 4),
        "available_credits_cents": status.available_credits_cents,
        "available_credits_dollars": round(status.available_credits_cents / 100, 2),
        "deficit_cents": status.deficit_cents,
        "deficit_dollars": round(status.deficit_cents / 100, 4),
        "total_images_requested": status.total_images_requested,
        "max_images_affordable": status.max_images_affordable,
        "warning_message": status.warning_message,
        "cost_breakdown": {
            "cost_per_image_cents": balancer.COST_PER_IMAGE_CENTS,
            "cost_per_claude_call_cents": balancer.COST_PER_CLAUDE_CALL_CENTS,
            "claude_calls": products if use_claude else 0,
            "image_calls": products * images_per_product,
        },
    }
