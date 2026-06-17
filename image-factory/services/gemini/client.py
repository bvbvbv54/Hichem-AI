from __future__ import annotations

import asyncio
from typing import Any

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from PIL import Image
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

# Use google_api_key with fallback to gemini_api_key / nano_banana_api_key
_api_key = settings.google_api_key or settings.gemini_api_key or settings.nano_banana_api_key
if _api_key:
    genai.configure(api_key=_api_key)


class GeminiClient:
    VISION_MODEL = settings.gemini_vision_model
    TEXT_MODEL = settings.gemini_text_model

    def __init__(self) -> None:
        self._vision_model = genai.GenerativeModel(self.VISION_MODEL)
        self._text_model = genai.GenerativeModel(self.TEXT_MODEL)

    @retry(
        retry=retry_if_exception_type((
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
        )),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(4),
    )
    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        response = await asyncio.to_thread(
            self._text_model.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(temperature=temperature),
        )
        return response.text

    @retry(
        retry=retry_if_exception_type((
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
        )),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(4),
    )
    async def generate_with_images(
        self,
        prompt: str,
        image_paths: list[str],
        temperature: float = 0.1,
    ) -> str:
        def _build_and_call() -> Any:
            parts: list[Any] = [prompt]
            for path in image_paths:
                img = Image.open(path)
                parts.append(img)
            return self._vision_model.generate_content(
                parts,
                generation_config=genai.GenerationConfig(temperature=temperature),
            )

        response = await asyncio.to_thread(_build_and_call)
        return response.text


gemini_client = GeminiClient()
