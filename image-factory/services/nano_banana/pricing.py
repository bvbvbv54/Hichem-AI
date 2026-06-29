from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.model_pricing import ModelPricing
from services.settings_service import get_setting
from configs.logging import get_logger

logger = get_logger(__name__)

SAFETY_BUFFER_DEFAULT = 1.20

SEED_PRICING = [
    {
        "model_id": "gemini-2.5-flash-image",
        "display_name": "Nano Banana",
        "provider": "google",
        "pricing_model": "token_based",
        "input_token_cost_per_million": 0.50,
        "output_token_cost_per_million": 30.0,
        "input_image_tokens": 2000,
        "output_tokens_by_resolution": {"1024": 1290},
        "default_resolution": "1024",
        "cost_per_output_image": 0.0,
        "cost_per_reference_image": 0.0,
        "deprecated": False,
        "notes": "~$0.039/image at 1024px, ~$0.001/input reference image",
    },
    {
        "model_id": "gemini-3.1-flash-image",
        "display_name": "Nano Banana 2",
        "provider": "google",
        "pricing_model": "token_based",
        "input_token_cost_per_million": 0.50,
        "output_token_cost_per_million": 60.0,
        "input_image_tokens": 1120,
        "output_tokens_by_resolution": {
            "512": 747,
            "1024": 1120,
            "2048": 1680,
            "4096": 2520,
        },
        "default_resolution": "1024",
        "cost_per_output_image": 0.0,
        "cost_per_reference_image": 0.0,
        "deprecated": False,
        "notes": "~$0.045/image at 512px, ~$0.067 at 1024px, ~$0.101 at 2048px, ~$0.151 at 4096px; ~$0.0006/input ref image",
    },
    {
        "model_id": "gemini-3-pro-image",
        "display_name": "Nano Banana Pro",
        "provider": "google",
        "pricing_model": "token_based",
        "input_token_cost_per_million": 2.00,
        "output_token_cost_per_million": 120.0,
        "input_image_tokens": 560,
        "output_tokens_by_resolution": {
            "1024": 1120,
            "2048": 1120,
            "4096": 2000,
        },
        "default_resolution": "1024",
        "cost_per_output_image": 0.0,
        "cost_per_reference_image": 0.0,
        "deprecated": False,
        "notes": "~$0.134/image at 1024px/2048px, ~$0.24 at 4096px; ~$0.0011/input ref image",
    },
    # Imagen 4 Standard (legacy)
    {
        "model_id": "imagen-4.0-generate-001",
        "display_name": "Imagen 4 Standard",
        "provider": "google",
        "pricing_model": "flat_rate",
        "cost_per_output_image": 0.02,
        "cost_per_reference_image": 0.0,
        "deprecated": True,
        "deprecation_date": date(2026, 4, 1),
        "sunset_date": date(2026, 8, 17),
        "deprecation_message": (
            "This model is marked as legacy in the system registry and may be removed "
            "after the configured sunset date. Migrate to newer models if available."
        ),
        "notes": "Imagen 4 Standard — flat-rate $0.02/image",
        "price_source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "price_checked_date": date(2026, 6, 29),
    },
    # Imagen 4 Fast (legacy)
    {
        "model_id": "imagen-4.0-fast-generate-001",
        "display_name": "Imagen 4 Fast",
        "provider": "google",
        "pricing_model": "flat_rate",
        "cost_per_output_image": 0.02,
        "cost_per_reference_image": 0.0,
        "deprecated": True,
        "deprecation_date": date(2026, 4, 1),
        "sunset_date": date(2026, 8, 17),
        "deprecation_message": (
            "This model is marked as legacy in the system registry and may be removed "
            "after the configured sunset date. Migrate to newer models if available."
        ),
        "notes": "Imagen 4 Fast — flat-rate $0.02/image",
        "price_source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "price_checked_date": date(2026, 6, 29),
    },
    # Imagen 4 Ultra (legacy)
    {
        "model_id": "imagen-4.0-ultra-generate-001",
        "display_name": "Imagen 4 Ultra",
        "provider": "google",
        "pricing_model": "flat_rate",
        "cost_per_output_image": 0.06,
        "cost_per_reference_image": 0.0,
        "deprecated": True,
        "deprecation_date": date(2026, 4, 1),
        "sunset_date": date(2026, 8, 17),
        "deprecation_message": (
            "This model is marked as legacy in the system registry and may be removed "
            "after the configured sunset date. Migrate to newer models if available."
        ),
        "notes": "Imagen 4 Ultra — flat-rate $0.06/image",
        "price_source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "price_checked_date": date(2026, 6, 29),
    },
]

_MIGRATION_SQL = [
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS pricing_model VARCHAR(32) NOT NULL DEFAULT 'token_based'",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS cost_per_output_image FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS cost_per_reference_image FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS deprecated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS deprecation_date DATE",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS deprecation_message TEXT DEFAULT ''",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS sunset_date DATE",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS price_source_url TEXT DEFAULT ''",
    "ALTER TABLE model_pricing ADD COLUMN IF NOT EXISTS price_checked_date DATE",
]


async def _run_migration(session: AsyncSession) -> None:
    for sql in _MIGRATION_SQL:
        try:
            await session.execute(sa_text(sql))
        except Exception as e:
            logger.warning("migration_sql_warning", sql=sql[:60], error=str(e))
    await session.commit()


async def seed_model_pricing(session: AsyncSession) -> None:
    await _run_migration(session)
    for row in SEED_PRICING:
        existing = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == row["model_id"])
        )
        if not existing.scalar_one_or_none():
            session.add(ModelPricing(**row))
    await session.commit()
    logger.info("model_pricing_seeded", count=len(SEED_PRICING))


async def get_model_pricing(
    session: AsyncSession, model_id: str
) -> Optional[ModelPricing]:
    result = await session.execute(
        select(ModelPricing).where(ModelPricing.model_id == model_id)
    )
    return result.scalar_one_or_none()


async def get_available_models(
    session: AsyncSession, as_of_date: Optional[date] = None
) -> list[ModelPricing]:
    if as_of_date is None:
        as_of_date = date.today()
    result = await session.execute(
        select(ModelPricing).where(
            sa_text(
                f"sunset_date IS NULL OR sunset_date > '{as_of_date.isoformat()}'"
            )
        ).order_by(ModelPricing.deprecated, ModelPricing.cost_per_output_image)
    )
    return list(result.scalars().all())


async def get_all_model_pricing(session: AsyncSession) -> list[ModelPricing]:
    result = await session.execute(
        select(ModelPricing).order_by(ModelPricing.deprecated, ModelPricing.cost_per_output_image)
    )
    return list(result.scalars().all())


async def get_safety_buffer(session: AsyncSession) -> float:
    val = await get_setting("cost_safety_buffer", session, str(SAFETY_BUFFER_DEFAULT))
    return float(val)


async def cost_estimate(
    session: AsyncSession,
    model_id: str,
    reference_count: int,
    output_count: int,
    resolution: str = "1024",
) -> dict[str, Any]:
    pricing = await get_model_pricing(session, model_id)
    if not pricing:
        return {
            "available": False,
            "error": f"No pricing found for model '{model_id}'",
            "pricing_model": "unknown",
            "input_cost_cents": 0.0,
            "output_cost_cents": 0.0,
            "subtotal_cents": 0.0,
            "safety_buffer_cents": 0.0,
            "total_cents": 0.0,
            "total_dollars": 0.0,
            "breakdown_lines": [],
        }

    pricing_model = (pricing.pricing_model or "token_based").lower()
    safety_multiplier = Decimal(str(await get_safety_buffer(session)))
    raw_input_cost = Decimal("0")
    raw_output_cost = Decimal("0")
    breakdown_lines = []

    if pricing_model == "flat_rate":
        raw_output_cost = Decimal(str(output_count)) * Decimal(str(pricing.cost_per_output_image))
        raw_input_cost = Decimal(str(reference_count)) * Decimal(str(pricing.cost_per_reference_image))

        ref_cost_display = pricing.cost_per_reference_image or 0.0
        out_cost_display = pricing.cost_per_output_image or 0.0
        if ref_cost_display > 0:
            breakdown_lines.append({
                "label": f"Reference images: {reference_count} × ${ref_cost_display:.4f}",
                "cost_cents": float(raw_input_cost * Decimal("100")),
            })
        breakdown_lines.append({
            "label": f"Output images: {output_count} × ${out_cost_display:.4f}",
            "cost_cents": float(raw_output_cost * Decimal("100")),
        })

    elif pricing_model == "input_output":
        raw_output_cost = Decimal(str(output_count)) * Decimal(str(pricing.cost_per_output_image))
        raw_input_cost = Decimal(str(reference_count)) * Decimal(str(pricing.cost_per_reference_image))

        if pricing.cost_per_reference_image > 0:
            breakdown_lines.append({
                "label": f"Reference images: {reference_count} × ${pricing.cost_per_reference_image:.4f}",
                "cost_cents": float(raw_input_cost * Decimal("100")),
            })
        breakdown_lines.append({
            "label": f"Output images: {output_count} × ${pricing.cost_per_output_image:.4f}",
            "cost_cents": float(raw_output_cost * Decimal("100")),
        })

    else:
        res_tokens = pricing.output_tokens_by_resolution.get(resolution)
        if res_tokens is None:
            sorted_res = sorted(pricing.output_tokens_by_resolution.keys(), key=int)
            resolution = sorted_res[0] if sorted_res else pricing.default_resolution
            res_tokens = pricing.output_tokens_by_resolution.get(resolution, 1120)

        input_cost_tokens = reference_count * pricing.input_image_tokens
        output_cost_tokens = output_count * res_tokens

        raw_input_cost = (
            Decimal(str(input_cost_tokens))
            * Decimal(str(pricing.input_token_cost_per_million))
            / Decimal("1000000")
        )
        raw_output_cost = (
            Decimal(str(output_cost_tokens))
            * Decimal(str(pricing.output_token_cost_per_million))
            / Decimal("1000000")
        )

        breakdown_lines = [
            {
                "label": f"Reference images: {reference_count} × "
                f"${Decimal(str(pricing.input_image_tokens * pricing.input_token_cost_per_million)) / Decimal('1000000'):.4f}",
                "cost_cents": float(raw_input_cost * Decimal("100")),
            },
            {
                "label": f"Output images: {output_count} × "
                f"${Decimal(str(res_tokens * pricing.output_token_cost_per_million)) / Decimal('1000000'):.4f} at {resolution}px",
                "cost_cents": float(raw_output_cost * Decimal("100")),
            },
        ]

    subtotal = raw_input_cost + raw_output_cost
    buffer_amount = subtotal * (safety_multiplier - Decimal("1"))
    total = subtotal * safety_multiplier

    return {
        "available": True,
        "model_id": model_id,
        "display_name": pricing.display_name,
        "pricing_model": pricing_model,
        "resolution": resolution,
        "input_cost_cents": float(raw_input_cost * Decimal("100")),
        "output_cost_cents": float(raw_output_cost * Decimal("100")),
        "subtotal_cents": float(subtotal * Decimal("100")),
        "safety_buffer_pct": round(float((safety_multiplier - Decimal("1")) * Decimal("100")), 0),
        "safety_buffer_cents": float(buffer_amount * Decimal("100")),
        "total_cents": float(total * Decimal("100")),
        "total_dollars": float(total),
        "breakdown_lines": breakdown_lines,
        "safety_buffer": float(safety_multiplier),
    }
