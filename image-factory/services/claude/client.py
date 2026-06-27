from __future__ import annotations

from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


class ClaudeClient:
    def __init__(self) -> None:
        self.api_key = settings.claude_api_key
        self.is_available = bool(self.api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.temperature = settings.claude_temperature
        self.base_url = "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=60.0,
        ) if self.is_available else None
        self._last_usage: dict | None = None

    @property
    def last_usage(self) -> dict | None:
        return self._last_usage

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    async def generate_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str],
        **kwargs: Any,
    ) -> str:
        if not self.is_available:
            raise RuntimeError("Claude is not available — no API key configured. Set CLAUDE_API_KEY or use a built-in prompt.")
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for path in image_paths:
            with open(path, "rb") as f:
                data = f.read()
            import base64
            encoded = base64.b64encode(data).decode("utf-8")
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else "png"
            media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            })
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        response = await self.client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()
        self._last_usage = data.get("usage", {})
        text_parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        return "\n".join(text_parts).strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    )
    async def generate_text(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        if not self.is_available:
            raise RuntimeError("Claude is not available — no API key configured.")
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        response = await self.client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        self._last_usage = data.get("usage", {})

        content = data.get("content", [])
        text_parts = [block.get("text", "") for block in content if block.get("type") == "text"]
        return "\n".join(text_parts).strip()

    async def generate_prompt(
        self,
        subject: str,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        system = (
            "You are an expert AI image prompt engineer. Your role is to create detailed, "
            "vivid, and effective prompts for image generation models. "
            "Output ONLY the prompt text, no explanations, no markdown formatting."
        )

        parts = [f"Create a detailed image generation prompt for: {subject}"]
        if style:
            parts.append(f"Style/Medium: {style}")
        if mood:
            parts.append(f"Mood/Atmosphere: {mood}")
        if context:
            parts.append(f"Context: {context}")
        parts.append(
            "\nInclude details about composition, lighting, color palette, camera angle, "
            "and technical quality indicators. The prompt should be 1-3 paragraphs."
        )

        user_prompt = "\n".join(parts)
        return await self.generate_text(system, user_prompt)

    async def enhance_prompt(
        self,
        original_prompt: str,
        style_guide: Optional[str] = None,
        brand_guidelines: Optional[str] = None,
    ) -> str:
        system = (
            "You are an expert AI image prompt enhancer. Take existing prompts and improve them "
            "with more detail, better structure, and optimal keywords for image generation. "
            "Enhance composition, lighting, color, and technical details. "
            "Output ONLY the enhanced prompt text, no explanations."
        )

        parts = [f"Enhance and improve this image generation prompt:\n\n{original_prompt}"]
        if style_guide:
            parts.append(f"\nStyle Guide to follow: {style_guide}")
        if brand_guidelines:
            parts.append(f"\nBrand Guidelines: {brand_guidelines}")
        parts.append("\nMake it more detailed and optimized for AI image generation.")

        user_prompt = "\n".join(parts)
        return await self.generate_text(system, user_prompt)

    async def optimize_for_platform(
        self,
        prompt: str,
        platform: str,
        aspect_ratio: Optional[str] = None,
    ) -> str:
        system = (
            "You are a marketing image prompt specialist. Optimize prompts for specific platforms. "
            f"Platform: {platform}. "
            "Output ONLY the optimized prompt."
        )

        user_prompt = f"Optimize this prompt for {platform}"
        if aspect_ratio:
            user_prompt += f" with aspect ratio {aspect_ratio}"
        user_prompt += f":\n\n{prompt}"

        return await self.generate_text(system, user_prompt)
