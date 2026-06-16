from __future__ import annotations

import asyncio
import hashlib
import json

from services.gemini.client import gemini_client
from configs.logging import get_logger

logger = get_logger(__name__)

OCR_PROMPT = """
Analyze this product image and detect any Chinese text (Simplified or Traditional).

Return ONLY a valid JSON object with no explanation, no markdown fences:
{
  "has_chinese": true,
  "labels": [
    {
      "text": "<original Chinese characters>",
      "position": "<top-left|top-center|top-right|center|bottom-left|bottom-center|bottom-right>",
      "context": "<what this label likely describes: feature, spec, quantity, brand, etc.>"
    }
  ]
}

If no Chinese text is found, return:
{"has_chinese": false, "labels": []}
"""


class OCRExtractor:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def scan_image(self, image_path: str) -> dict:
        image_hash = await asyncio.to_thread(self._sha256, image_path)
        cache_key = f"ocr:result:{image_hash}"
        cached = await self._redis.get(cache_key)
        if cached:
            logger.debug("ocr_cache_hit", image_hash=image_hash)
            return json.loads(cached)
        raw = await gemini_client.generate_with_images(OCR_PROMPT, [image_path])
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(cleaned)
        await self._redis.setex(cache_key, 86400, json.dumps(result))
        return result

    async def scan_all(self, image_paths: list[str]) -> list[dict]:
        return await asyncio.gather(*[self.scan_image(p) for p in image_paths])

    @staticmethod
    def _sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
