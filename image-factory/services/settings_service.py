from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.setting import Setting
from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "app."


async def get_setting(key: str, session: AsyncSession, fallback: Any = "") -> str:
    db_key = f"{_KEY_PREFIX}{key}"
    result = await session.execute(select(Setting).where(Setting.key == db_key))
    row = result.scalar_one_or_none()
    if row and row.value:
        return row.value
    env_val = getattr(settings, key, None)
    if env_val is not None:
        return str(env_val)
    return str(fallback) if fallback != "" else ""


async def get_setting_with_source(key: str, session: AsyncSession, fallback: Any = "") -> tuple[str, str]:
    db_key = f"{_KEY_PREFIX}{key}"
    result = await session.execute(select(Setting).where(Setting.key == db_key))
    row = result.scalar_one_or_none()
    if row and row.value:
        return row.value, "database"
    env_val = getattr(settings, key, None)
    if env_val is not None and env_val != "":
        return str(env_val), "env_file"
    fb = str(fallback) if fallback != "" else ""
    return fb, "default"


async def set_setting(key: str, value: str, session: AsyncSession) -> None:
    db_key = f"{_KEY_PREFIX}{key}"
    result = await session.execute(select(Setting).where(Setting.key == db_key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=db_key, value=value))
    await session.commit()
    logger.info("setting_updated", key=key)


async def get_provider_api_key(key_name: str, session: AsyncSession) -> str:
    return await get_setting(key_name, session)


async def set_provider_api_key(key_name: str, value: str, session: AsyncSession) -> None:
    await set_setting(key_name, value, session)
    logger.info("provider_key_updated", key=key_name)


async def get_google_api_key(session: AsyncSession) -> tuple[str, str]:
    """Read google_api_key with fallback to gemini_api_key / nano_banana_api_key for backward compat."""
    val, src = await get_setting_with_source("google_api_key", session)
    if val:
        return val, src
    val, src = await get_setting_with_source("gemini_api_key", session)
    if val:
        return val, src
    val, src = await get_setting_with_source("nano_banana_api_key", session)
    if val:
        return val, src
    return "", "default"


async def set_google_api_key(value: str, session: AsyncSession) -> None:
    """Write google_api_key (also back-fill gemini_api_key for legacy consumers)."""
    await set_setting("google_api_key", value, session)
    # back-fill legacy keys so existing consumers still work
    await set_setting("gemini_api_key", value, session)
    await set_setting("nano_banana_api_key", value, session)


async def get_provider_keys_status(session: AsyncSession) -> dict:
    keys = ["google_api_key", "claude_api_key", "openrouter_api_key"]
    result = {}
    for key in keys:
        if key == "google_api_key":
            val, src = await get_google_api_key(session)
        else:
            val, src = await get_setting_with_source(key, session)
        result[key] = {
            "configured": bool(val),
            "masked": val[:8] + "..." + val[-4:] if len(val) > 12 else "",
            "source": src,
        }
    return result


async def get_claude_config(session: AsyncSession) -> dict:
    model, model_src = await get_setting_with_source("claude_model", session, "claude-sonnet-4-20250514")
    tokens, tokens_src = await get_setting_with_source("claude_max_tokens", session, "4096")
    temp, temp_src = await get_setting_with_source("claude_temperature", session, "0.7")
    return {
        "claude_model": {"value": model, "source": model_src},
        "claude_max_tokens": {"value": int(tokens), "source": tokens_src},
        "claude_temperature": {"value": float(temp), "source": temp_src},
    }


async def set_claude_config(model: str, max_tokens: int, temperature: float, session: AsyncSession) -> None:
    await set_setting("claude_model", model, session)
    await set_setting("claude_max_tokens", str(max_tokens), session)
    await set_setting("claude_temperature", str(temperature), session)


# Pricing is now internal only — read from configs/pricing.py


AVAILABLE_IMG2IMG_MODELS = [
    {"id": "google/imagen-4", "name": "Google Imagen 4", "provider": "replicate"},
    {"id": "google-nano-banana", "name": "Google Nano Banana (Imagen)", "provider": "google"},
    {"id": "stability-ai/sdxl", "name": "Stability AI SDXL", "provider": "replicate"},
    {"id": "stability-ai/stable-diffusion-3.5", "name": "Stable Diffusion 3.5", "provider": "replicate"},
    {"id": "black-forest-labs/flux-dev", "name": "FLUX.1 Dev", "provider": "replicate"},
    {"id": "black-forest-labs/flux-schnell", "name": "FLUX.1 Schnell", "provider": "replicate"},
    {"id": "dall-e-3", "name": "OpenAI DALL-E 3", "provider": "openai"},
]

IMG2IMG_MODEL_IDS = [m["id"] for m in AVAILABLE_IMG2IMG_MODELS]


async def get_img2img_config(session: AsyncSession) -> dict:
    model, model_src = await get_setting_with_source("img2img_model", session, "google/imagen-4")
    return {
        "img2img_model": {"value": model, "source": model_src},
        "available_models": AVAILABLE_IMG2IMG_MODELS,
    }


async def set_img2img_config(model: str, session: AsyncSession) -> None:
    if model not in IMG2IMG_MODEL_IDS:
        raise ValueError(f"Unknown model: {model}. Available: {', '.join(IMG2IMG_MODEL_IDS)}")
    await set_setting("img2img_model", model, session)


async def get_storage_config(session: AsyncSession) -> dict:
    path, path_src = await get_setting_with_source("storage_local_path", session, settings.storage_local_path)
    enabled, enabled_src = await get_setting_with_source("storage_enabled", session, "true" if settings.storage_enabled else "false")
    return {
        "storage_local_path": {"value": path, "source": path_src},
        "storage_enabled": {"value": enabled.lower() == "true", "source": enabled_src},
    }


async def set_storage_config(path: str, session: AsyncSession) -> None:
    await set_setting("storage_local_path", path, session)


async def set_storage_enabled(enabled: bool, session: AsyncSession) -> None:
    await set_setting("storage_enabled", "true" if enabled else "false", session)


async def get_all_settings(session: AsyncSession) -> dict:
    """Return all configurable settings grouped by category."""
    provider_keys = await get_provider_keys_status(session)
    claude_cfg = await get_claude_config(session)
    img2img = await get_img2img_config(session)
    storage = await get_storage_config(session)
    budget, budget_src = await get_setting_with_source("monthly_budget_cents", session, str(settings.monthly_budget_cents))

    return {
        "provider_keys": provider_keys,
        "claude": claude_cfg,
        "img2img": img2img,
        "storage": storage,
        "monthly_budget_cents": {"value": int(budget), "source": budget_src},
    }
