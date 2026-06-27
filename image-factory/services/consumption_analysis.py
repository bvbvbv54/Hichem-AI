from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from configs.logging import get_logger

logger = get_logger(__name__)

NANOBANANA_API_URL = "https://api.nanobanana.com/v1"
GOOGLE_AI_STUDIO_URL = "https://aistudio.google.com/apikey"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@dataclass
class ProviderPricing:
    provider: str
    model: str
    input_per_million: float
    output_per_million: float
    image_cost_per_image: float | None = None
    source_url: str = ""


async def fetch_openrouter_models() -> list[ProviderPricing]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(OPENROUTER_MODELS_URL, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("openrouter_models_fetch_failed", error=str(e))
        return []

    pricings = []
    for model in data.get("data", []):
        model_id = model.get("id", "")
        pricing_info = model.get("pricing", {})
        input_price = float(pricing_info.get("prompt", 0)) * 1_000_000
        output_price = float(pricing_info.get("completion", 0)) * 1_000_000
        image_cost = float(pricing_info.get("image", 0)) if pricing_info.get("image") else None

        pricings.append(ProviderPricing(
            provider="openrouter",
            model=model_id,
            input_per_million=round(input_price, 6),
            output_per_million=round(output_price, 6),
            image_cost_per_image=image_cost,
            source_url=OPENROUTER_MODELS_URL,
        ))
    return pricings


def get_nanobanana_post_template() -> dict[str, Any]:
    return {
        "endpoint": f"{NANOBANANA_API_URL}/generate",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer YOUR_NANOBANANA_API_KEY",
        },
        "body": {
            "model": "flux-schnell",
            "input": {
                "prompt": "Professional product photograph of {product_name}. High quality, white background.",
                "num_outputs": 1,
                "width": 1024,
                "height": 1024,
                "guidance_scale": 7.5,
                "num_inference_steps": 30,
            },
        },
        "description": "NanoBanana API (Replicate-compatible) - image generation via Flux model",
    }


def get_google_ai_studio_post_template() -> dict[str, Any]:
    return {
        "endpoint": "https://aistudio.google.com/v1beta/models/{model}:streamGenerateContent",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer YOUR_GOOGLE_AI_STUDIO_KEY",
        },
        "body": {
            "contents": [{"role": "user", "parts": [{"text": "Generate a professional e-commerce product image of {product_name}. Clean white background, studio lighting, commercial quality."}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 1,
                "topP": 1.0,
                "maxOutputTokens": 4096,
            },
        },
        "query_params": {"alt": "sse"},
        "description": "Google AI Studio - stream generate content (SSE streaming)",
    }


def estimate_cost(pricing: list[ProviderPricing], input_tokens: int = 1000, output_tokens: int = 1000, num_images: int = 1) -> list[dict]:
    estimates = []
    for p in pricing:
        input_cost = (input_tokens / 1_000_000) * p.input_per_million
        output_cost = (output_tokens / 1_000_000) * p.output_per_million
        image_cost = (p.image_cost_per_image or 0) * num_images
        total_cost = round(input_cost + output_cost + image_cost, 10)
        estimates.append({
            "provider": p.provider,
            "model": p.model,
            "pricing_per_million": {
                "input": p.input_per_million,
                "output": p.output_per_million,
                "image": p.image_cost_per_image,
            },
            "estimated_cost": {
                "input_tokens_cost": round(input_cost, 10),
                "output_tokens_cost": round(output_cost, 10),
                "image_cost": round(image_cost, 10),
                "total_cost_usd": total_cost,
                "total_cost_cents": round(total_cost * 100, 2),
            },
            "source_url": p.source_url,
        })
    return estimates
