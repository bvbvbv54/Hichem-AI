from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from configs.logging import get_logger
from services.nano_banana.credit_balancer import get_credit_balancer
from services.settings_service import get_setting_with_source
from services.nano_banana.pricing import cost_estimate, get_model_pricing, get_available_models, get_all_model_pricing

logger = get_logger(__name__)

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/status")
async def credit_status(session: AsyncSession = Depends(get_session)):
    balancer = get_credit_balancer()
    key_validation = await balancer.validate_api_key(session)
    balance = await balancer.check_balance(session)
    used = await balancer.get_total_usage_cents(session)
    estimate = balancer.estimate_cost(product_count=1, images_per_product=1)

    budget_val, budget_src = await get_setting_with_source("monthly_budget_cents", session)
    budget_cents = int(budget_val) if budget_val else 10000

    return {
        "api_key_configured": key_validation.get("valid", False),
        "api_key_valid": key_validation.get("valid", False),
        "available_credits_cents": balance,
        "available_credits_dollars": round(balance / 100, 2),
        "used_credits_cents": used,
        "used_credits_dollars": round(used / 100, 2),
        "monthly_budget_cents": budget_cents,
        "monthly_budget_dollars": round(budget_cents / 100, 2),
        "budget_source": budget_src,
        "cost_per_image_cents": estimate.cost_per_image_cents,
        "estimated_cost_per_product_cents": estimate.estimated_cost_cents,
        "estimated_cost_per_product_dollars": round(estimate.estimated_cost_cents / 100, 4),
        "smoke_test_mode": False,
    }


@router.get("/models")
async def list_model_pricing(
    as_of_date: str = Query(default="", description="ISO date for sunset filtering (empty = today)"),
    include_hidden: bool = Query(default=False, description="Include post-sunset models"),
    session: AsyncSession = Depends(get_session),
):
    if as_of_date:
        from datetime import date as dt_date
        filter_date = dt_date.fromisoformat(as_of_date)
    else:
        from datetime import date as dt_date
        filter_date = dt_date.today()

    if include_hidden:
        models = await get_all_model_pricing(session)
    else:
        models = await get_available_models(session, filter_date)

    result = []
    for m in models:
        entry = {
            "model_id": m.model_id,
            "display_name": m.display_name,
            "provider": m.provider,
            "pricing_model": m.pricing_model or "token_based",
            "cost_per_output_image": m.cost_per_output_image or 0.0,
            "cost_per_reference_image": m.cost_per_reference_image or 0.0,
            "deprecated": m.deprecated or False,
            "deprecation_date": m.deprecation_date.isoformat() if m.deprecation_date else None,
            "deprecation_message": m.deprecation_message or "",
            "sunset_date": m.sunset_date.isoformat() if m.sunset_date else None,
            "is_hidden": False,
        }
        if m.sunset_date:
            entry["is_hidden"] = filter_date >= m.sunset_date
        result.append(entry)
    return {"models": result}


@router.get("/estimate")
async def credit_estimate(
    products: int = 1,
    images_per_product: int = 1,
    model_id: str = Query(default="", description="Nano Banana model ID for token-based estimate"),
    reference_count: int = Query(default=3, description="Number of reference images per product"),
    resolution: str = Query(default="1024", description="Output resolution (512, 1024, 2048, 4096)"),
    session: AsyncSession = Depends(get_session),
):
    balancer = get_credit_balancer()
    balance = await balancer.check_balance(session)
    budget_cents = balance + (await balancer.get_total_usage_cents(session))

    if model_id:
        pricing = await get_model_pricing(session, model_id)
        if not pricing:
            return {"available": False, "error": f"Unknown model: {model_id}"}
        total_refs = products * reference_count
        total_output = products * images_per_product
        estimate = await cost_estimate(
            session, model_id, total_refs, total_output, resolution
        )
        total_cost_cents = estimate["total_cents"]
        deficit = max(0, total_cost_cents - balance)
        max_affordable = 0
        if estimate["total_cents"] > 0:
            unit_cost = estimate["total_cents"] / (products or 1)
            max_affordable = int(balance / unit_cost) if unit_cost > 0 else 0
        remaining = max(0, budget_cents - total_cost_cents)
        pct = round((total_cost_cents / budget_cents) * 100, 1) if budget_cents > 0 else 0
        require_confirmation = total_cost_cents > balance or remaining < 100.0

        return {
            "available": True,
            "model_id": model_id,
            "display_name": estimate["display_name"],
            "resolution": resolution,
            "estimated_cost_cents": estimate["total_cents"],
            "estimated_cost_dollars": round(estimate["total_cents"] / 100, 4),
            "available_credits_cents": balance,
            "available_credits_dollars": round(balance / 100, 2),
            "deficit_cents": deficit,
            "deficit_dollars": round(deficit / 100, 4),
            "total_products": products,
            "total_images_requested": products * images_per_product,
            "max_images_affordable": max_affordable,
            "require_confirmation": require_confirmation,
            "cost_breakdown": {
                "model": estimate["display_name"],
                "reference_count": total_refs,
                "output_count": total_output,
                "resolution": resolution,
                "input_cost_cents": estimate["input_cost_cents"],
                "output_cost_cents": estimate["output_cost_cents"],
                "subtotal_cents": estimate["subtotal_cents"],
                "safety_buffer_pct": estimate["safety_buffer_pct"],
                "safety_buffer_cents": estimate["safety_buffer_cents"],
                "total_cents": estimate["total_cents"],
                "lines": estimate["breakdown_lines"],
            },
            "usage_percent": pct,
        }
    else:
        status = await balancer.check_sufficient_credits(session, products, images_per_product)
        return {
            "available": True,
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
                "image_calls": products * images_per_product,
            },
        }
