from __future__ import annotations

from fastapi import APIRouter, Query

from configs.logging import get_logger
from services.consumption_analysis import (
    fetch_openrouter_models,
    get_nanobanana_post_template,
    get_google_ai_studio_post_template,
    estimate_cost,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/consumption", tags=["Consumption"])


@router.get("/analysis")
async def consumption_analysis(
    input_tokens: int = Query(1000, description="Estimated input tokens per call"),
    output_tokens: int = Query(1000, description="Estimated output tokens per call"),
    num_images: int = Query(1, description="Number of images to generate"),
):
    openrouter_models = await fetch_openrouter_models()

    estimates = estimate_cost(openrouter_models, input_tokens, output_tokens, num_images)

    nanobanana_template = get_nanobanana_post_template()
    ai_studio_template = get_google_ai_studio_post_template()

    return {
        "parameters": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "num_images": num_images,
        },
        "pricing_fetched_from": {
            "openrouter": "https://openrouter.ai/api/v1/models",
        },
        "estimates": estimates,
        "post_templates": {
            "nano_banana": nanobanana_template,
            "google_ai_studio": ai_studio_template,
        },
    }
