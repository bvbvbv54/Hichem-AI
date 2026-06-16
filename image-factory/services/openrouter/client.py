from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Optional

import httpx

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

IMAGE_MODELS = [
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-image-preview",
    "google/gemini-3-pro-image-preview",
    "black-forest-labs/flux.2-pro",
    "openai/gpt-5.4-image-2",
]

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_SUPPORTED_RATIOS = {
    (1024, 1024): "1:1",
    (832, 1248): "2:3",
    (1248, 832): "3:2",
    (864, 1184): "3:4",
    (1184, 864): "4:3",
    (896, 1152): "4:5",
    (1152, 896): "5:4",
    (768, 1344): "9:16",
    (1344, 768): "16:9",
    (1536, 672): "21:9",
}


def _aspect_ratio(width: int, height: int) -> str | None:
    return _SUPPORTED_RATIOS.get((width, height))


class OpenRouterClient:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.timeout = settings.openrouter_timeout
        self.max_retries = settings.openrouter_max_retries

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_images: int = 1,
        reference_image_path: Optional[str] = None,
    ) -> tuple[list[bytes], dict | None]:
        last_error = None
        for model in IMAGE_MODELS:
            try:
                logger.info("openrouter_trying_model", model=model)
                images, usage = await self._call_model(
                    model=model,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    num_images=num_images,
                    reference_image_path=reference_image_path,
                )
                if images:
                    return images, usage
            except Exception as e:
                logger.warning("openrouter_model_failed", model=model, error=str(e))
                last_error = e
                continue
        raise RuntimeError(f"All OpenRouter models failed. Last error: {last_error}")

    async def _call_model(
        self,
        model: str,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        num_images: int,
        reference_image_path: Optional[str] = None,
    ) -> tuple[list[bytes], dict | None]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        message_content: list[dict] = [{"type": "text", "text": full_prompt}]

        if reference_image_path:
            ref_path = Path(reference_image_path)
            if ref_path.exists():
                with open(ref_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": message_content}],
            "modalities": ["image", "text"],
        }

        ratio = _aspect_ratio(width, height)
        if ratio:
            body["image_config"] = {"aspect_ratio": ratio}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=body,
            )

            if response.status_code == 429:
                logger.warning("openrouter_rate_limited", model=model)
                await asyncio.sleep(5)
                response = await client.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers=headers,
                    json=body,
                )

            if response.status_code != 200:
                logger.error("openrouter_error", model=model, status=response.status_code, body=response.text[:500])
                response.raise_for_status()

            data = response.json()
            actual_model = data.get("model", model)
            usage = data.get("usage", {})
            usage["model"] = actual_model
            images = []
            choices = data.get("choices", [])
            for choice in choices:
                msg = choice.get("message", {})
                for img in msg.get("images", []):
                    url = img.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        b64_str = url.split(",", 1)[1]
                        images.append(base64.b64decode(b64_str))

            return images, usage
