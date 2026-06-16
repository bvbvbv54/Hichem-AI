from __future__ import annotations

import asyncio
import io
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from configs.settings import settings
from configs.logging import get_logger
from services.nano_banana.models import GenerationRequest, GenerationResult

logger = get_logger(__name__)


class BaseImageProvider(ABC):
    """Abstract base for image generation providers."""

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        ...

    @abstractmethod
    async def check_health(self) -> bool:
        ...


class ReplicateProvider(BaseImageProvider):
    def __init__(self) -> None:
        self.api_key = settings.replicate_api_key
        self.poll_interval = settings.image_provider_poll_interval
        self.client = httpx.AsyncClient(
            base_url="https://api.replicate.com/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self.default_model = "google/imagen-4"

    async def close(self) -> None:
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(settings.image_provider_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    )
    async def _create_prediction(self, request: GenerationRequest) -> dict[str, Any]:
        model = request.model or self.default_model
        input_data: dict[str, Any] = {
            "prompt": request.prompt,
        }
        if request.negative_prompt:
            input_data["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            input_data["seed"] = request.seed
        if request.steps:
            input_data["num_inference_steps"] = request.steps
        if request.guidance_scale:
            input_data["guidance_scale"] = request.guidance_scale
        input_data.update(request.extra_params)

        # Use model-based prediction endpoint for newer models
        response = await self.client.post(f"/models/{model}/predictions", json={"input": input_data})
        response.raise_for_status()
        return response.json()

    async def _poll_prediction(self, prediction_id: str, timeout: int = 300) -> dict[str, Any]:
        start = time.time()
        while time.time() - start < timeout:
            response = await self.client.get(f"/predictions/{prediction_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status == "succeeded":
                return data
            if status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"Replicate generation failed: {error}")
            if status == "canceled":
                raise RuntimeError("Replicate generation was canceled")
            await asyncio.sleep(self.poll_interval)
        raise TimeoutError(f"Replicate prediction {prediction_id} timed out")

    async def _download_image(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        prediction = await self._create_prediction(request)
        prediction_id = prediction.get("id")
        if not prediction_id:
            raise RuntimeError("No prediction ID returned")

        result = await self._poll_prediction(prediction_id, timeout=settings.image_provider_timeout)

        outputs = result.get("output", [])
        if isinstance(outputs, str):
            outputs = [outputs]

        results = []
        for url in outputs:
            image_bytes = await self._download_image(url)
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            results.append(GenerationResult(
                image_data=image_bytes,
                width=w,
                height=h,
                metadata={"provider": "replicate", "model": "google/imagen-4", "prediction_id": prediction_id},
            ))

        return results

    async def check_health(self) -> bool:
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception:
            return False


class StabilityAIProvider(BaseImageProvider):
    def __init__(self) -> None:
        self.api_key = settings.stabilityai_api_key
        self.client = httpx.AsyncClient(
            base_url="https://api.stability.ai/v2beta",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=60.0,
        )

    async def close(self) -> None:
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(settings.image_provider_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        payload = {
            "text_prompts": [{"text": request.prompt, "weight": 1.0}],
            "cfg_scale": request.guidance_scale,
            "steps": request.steps,
            "samples": request.num_images,
        }
        if request.negative_prompt:
            payload["text_prompts"].append({"text": request.negative_prompt, "weight": -1.0})
        if request.seed is not None:
            payload["seed"] = request.seed

        response = await self.client.post(
            f"/stable-image/generate/ultra",
            json=payload,
            params={"output_format": "png"},
        )
        response.raise_for_status()
        data = response.json()

        results = []
        artifacts = data.get("artifacts", [])
        for art in artifacts:
            import base64
            image_bytes = base64.b64decode(art["base64"])
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            results.append(GenerationResult(
                image_data=image_bytes,
                width=w,
                height=h,
                seed=art.get("seed"),
                mime_type=f"image/{art.get('finishReason', 'png').lower()}",
            ))

        return results

    async def check_health(self) -> bool:
        try:
            response = await self.client.get("/user/account")
            return response.status_code == 200
        except Exception:
            return False


class OpenAIProvider(BaseImageProvider):
    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def close(self) -> None:
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(settings.image_provider_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        # DALL-E 3 only supports 1 image per call
        all_results: list[GenerationResult] = []
        remaining = request.num_images

        while remaining > 0:
            n = min(remaining, 1)
            payload = {
                "model": request.model or "dall-e-3",
                "prompt": request.prompt,
                "n": n,
                "size": f"{request.width}x{request.height}",
                "response_format": "b64_json",
                "quality": "standard",
            }
            if request.negative_prompt:
                logger.warning("DALL-E does not support negative prompts, ignoring")

            response = await self.client.post("/images/generations", json=payload)
            response.raise_for_status()
            data = response.json()

            for item in data.get("data", []):
                import base64
                image_bytes = base64.b64decode(item["b64_json"])
                img = Image.open(io.BytesIO(image_bytes))
                w, h = img.size
                all_results.append(GenerationResult(
                    image_data=image_bytes,
                    width=w,
                    height=h,
                    metadata={"revised_prompt": item.get("revised_prompt", "")},
                ))

            remaining -= n

        return all_results

    async def check_health(self) -> bool:
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception:
            return False


class NanoBananaClient:
    """
    Facade for image generation. Delegates to the configured provider.
    This isolates the rest of the system from specific provider implementations.
    """

    def __init__(self) -> None:
        self.provider = self._create_provider()

    def _create_provider(self) -> BaseImageProvider:
        provider_map: dict[str, type[BaseImageProvider]] = {
            "replicate": ReplicateProvider,
            "stabilityai": StabilityAIProvider,
            "openai": OpenAIProvider,
        }
        provider_type = settings.image_provider
        provider_cls = provider_map.get(provider_type)
        if not provider_cls:
            raise ValueError(f"Unknown image provider: {provider_type}")
        return provider_cls()

    async def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        logger.info("generating_images", provider=settings.image_provider, prompt=request.prompt[:80])
        return await self.provider.generate(request)

    async def generate_image_to_image(
        self,
        prompt: str,
        negative_prompt: str,
        reference_image_path: str,
        seed: int = 0,
    ) -> bytes:
        logger.info("image_to_image", provider=settings.image_provider, reference=reference_image_path)
        import base64
        with open(reference_image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        request = GenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=1,
            seed=seed,
            extra_params={"reference_image": encoded},
        )
        results = await self.provider.generate(request)
        if not results:
            raise RuntimeError("Image-to-image generation returned no results")
        return results[0].image_data

    async def check_health(self) -> bool:
        return await self.provider.check_health()

    async def close(self) -> None:
        if hasattr(self.provider, "close"):
            await self.provider.close()


def get_image_provider() -> NanoBananaClient:
    return NanoBananaClient()
