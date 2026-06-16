from __future__ import annotations

MODEL_PRICING = {
    # Anthropic Claude models (per million tokens, in USD)
    "claude-sonnet-4-20250514": {"input_per_million": 3.0, "output_per_million": 15.0, "provider": "anthropic"},
    "claude-sonnet-4": {"input_per_million": 3.0, "output_per_million": 15.0, "provider": "anthropic"},
    "claude-3-opus-latest": {"input_per_million": 15.0, "output_per_million": 75.0, "provider": "anthropic"},
    "claude-3-opus-20240229": {"input_per_million": 15.0, "output_per_million": 75.0, "provider": "anthropic"},
    "claude-3-sonnet-20240229": {"input_per_million": 3.0, "output_per_million": 15.0, "provider": "anthropic"},
    "claude-3-haiku-20240307": {"input_per_million": 0.25, "output_per_million": 1.25, "provider": "anthropic"},
    "claude-3-5-sonnet-20241022": {"input_per_million": 3.0, "output_per_million": 15.0, "provider": "anthropic"},
    "claude-3-5-haiku-20241022": {"input_per_million": 0.80, "output_per_million": 4.0, "provider": "anthropic"},

    # OpenAI models
    "gpt-4o": {"input_per_million": 2.50, "output_per_million": 10.0, "provider": "openai"},
    "gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60, "provider": "openai"},
    "gpt-4-turbo": {"input_per_million": 10.0, "output_per_million": 30.0, "provider": "openai"},
    "gpt-4": {"input_per_million": 30.0, "output_per_million": 60.0, "provider": "openai"},
    "gpt-3.5-turbo": {"input_per_million": 0.50, "output_per_million": 1.50, "provider": "openai"},
    "dall-e-3": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openai", "image_cost_per_image": 0.040},
    "dall-e-2": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openai", "image_cost_per_image": 0.020},

    # OpenRouter image generation models
    "google/gemini-2.5-flash-image": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openrouter", "image_cost_per_image": 0.003},
    "google/gemini-3.1-flash-image-preview": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openrouter", "image_cost_per_image": 0.005},
    "google/gemini-3-pro-image-preview": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openrouter", "image_cost_per_image": 0.010},
    "black-forest-labs/flux.2-pro": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openrouter", "image_cost_per_image": 0.008},
    "openai/gpt-5.4-image-2": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "openrouter", "image_cost_per_image": 0.006},

    # Replicate models
    "black-forest-labs/flux-schnell": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "replicate", "image_cost_per_image": 0.003},
    "black-forest-labs/flux-dev": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "replicate", "image_cost_per_image": 0.025},
    "black-forest-labs/flux-pro": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "replicate", "image_cost_per_image": 0.050},
    "stabilityai/stable-diffusion-3.5": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "replicate", "image_cost_per_image": 0.035},
    "stabilityai/stable-diffusion-3": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "replicate", "image_cost_per_image": 0.025},

    # StabilityAI
    "stable-image-ultra": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "stabilityai", "image_cost_per_image": 0.080},
    "stable-image-core": {"input_per_million": 0.0, "output_per_million": 0.0, "provider": "stabilityai", "image_cost_per_image": 0.035},
}

STORAGE_COST_PER_GB_PER_MONTH = 0.023

DEFAULT_TEXT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_IMAGE_MODEL = "flux"

PRICING_FALLBACK_TEXT_PER_1K = 0.003
PRICING_FALLBACK_IMAGE = 0.02


def get_model_pricing(model_name: str) -> dict:
    if model_name in MODEL_PRICING:
        return MODEL_PRICING[model_name]
    return {
        "input_per_million": PRICING_FALLBACK_TEXT_PER_1K * 1000,
        "output_per_million": PRICING_FALLBACK_TEXT_PER_1K * 1000,
        "provider": "unknown",
        "image_cost_per_image": PRICING_FALLBACK_IMAGE,
    }


def compute_text_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = get_model_pricing(model_name)
    input_cost = (input_tokens / 1_000_000) * pricing.get("input_per_million", 0)
    output_cost = (output_tokens / 1_000_000) * pricing.get("output_per_million", 0)
    return round(input_cost + output_cost, 10)


def compute_image_cost(model_name: str, num_images: int = 1) -> float:
    pricing = get_model_pricing(model_name)
    cost_per_image = pricing.get("image_cost_per_image", 0)
    return round(cost_per_image * num_images, 10)

