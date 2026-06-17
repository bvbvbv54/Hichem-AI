from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from configs.logging import get_logger

logger = get_logger(__name__)


class ImageIntelligence:
    async def analyze_image(self, image_path: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": image_path,
            "hash": "",
            "color_palette": [],
            "has_text": False,
            "dimensions": None,
            "format": "",
        }

        try:
            from PIL import Image as PILImage
            img = PILImage.open(image_path)
            result["format"] = img.format or ""
            result["dimensions"] = {"width": img.width, "height": img.height}
            result["hash"] = await self._compute_image_hash(image_path)
            result["color_palette"] = await self._extract_color_palette(img)
        except Exception as exc:
            logger.warning("image_analysis_failed", path=image_path, error=str(exc))

        return result

    async def _compute_image_hash(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:32]

    async def _extract_color_palette(self, img: Any, num_colors: int = 5) -> list[str]:
        try:
            from PIL import Image as PILImage
            small = img.resize((100, 100))
            colors = small.getcolors(10000)
            if colors:
                sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
                return [f"#{c[1][0]:02x}{c[1][1]:02x}{c[1][2]:02x}" for _, c in sorted_colors[:num_colors]]
        except Exception:
            pass
        return []

    async def generate_image_embedding(self, image_path: str) -> list[float]:
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image_path)
            img = img.convert("RGB").resize((224, 224))
            pixels = list(img.getdata())
            avg_r = sum(p[0] for p in pixels) / len(pixels)
            avg_g = sum(p[1] for p in pixels) / len(pixels)
            avg_b = sum(p[2] for p in pixels) / len(pixels)
            import hashlib
            seed = hashlib.sha256(f"{avg_r:.2f}{avg_g:.2f}{avg_b:.2f}".encode()).digest()
            import random
            rng = random.Random(seed)
            return [rng.gauss(avg_r / 255, 0.1) for _ in range(64)]
        except Exception as exc:
            logger.warning("image_embedding_failed", path=image_path, error=str(exc))
            import hashlib, random
            rng = random.Random(hashlib.sha256(image_path.encode()).digest())
            return [rng.gauss(0, 0.1) for _ in range(64)]

    async def find_visually_similar(
        self,
        query_embedding: list[float],
        image_embeddings: dict[str, list[float]],
        threshold: float = 0.7,
    ) -> list[tuple[str, float]]:
        def cosine_sim(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(y * y for y in b) ** 0.5
            return dot / (na * nb) if na and nb else 0.0

        results: list[tuple[str, float]] = []
        for path, emb in image_embeddings.items():
            sim = cosine_sim(query_embedding, emb)
            if sim >= threshold:
                results.append((path, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def extract_visual_features(self, image_path: str) -> dict[str, Any]:
        features: dict[str, Any] = {
            "path": image_path,
            "brightness": 0.0,
            "contrast": 0.0,
            "is_white_background": False,
            "dominant_colors": [],
            "estimated_product_type": "",
        }
        try:
            from PIL import Image as PILImage, ImageStat
            img = PILImage.open(image_path).convert("RGB")
            stat = ImageStat.Stat(img)
            features["brightness"] = round(sum(stat.mean) / 3 / 255, 4)
            features["contrast"] = round(sum(stat.stddev) / 3 / 255, 4)
            features["dominant_colors"] = await self._extract_color_palette(img, 3)
            if features["brightness"] > 0.9 and features["contrast"] < 0.15:
                features["is_white_background"] = True
            features["estimated_product_type"] = self._estimate_product_type(features)
        except Exception as exc:
            logger.warning("visual_features_failed", path=image_path, error=str(exc))
        return features

    def _estimate_product_type(self, features: dict[str, Any]) -> str:
        if features.get("is_white_background"):
            return "studio_photography"
        if features.get("brightness", 0) > 0.7:
            return "well_lit_product"
        if features.get("contrast", 0) > 0.3:
            return "high_contrast_product"
        return "general_product"
