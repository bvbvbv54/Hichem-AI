from __future__ import annotations

import io
from typing import Any, Optional

from PIL import Image

from services.claude.client import ClaudeClient
from configs.logging import get_logger

logger = get_logger(__name__)


class ImageAnalyzer:
    """
    Analyzes supplier product images to extract visual information
    for premium image generation.
    """

    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def analyze(self, image_data: bytes) -> dict[str, Any]:
        """Analyze a single product image."""
        img = Image.open(io.BytesIO(image_data))
        width, height = img.size
        format_name = img.format or "unknown"
        mode = img.mode

        # Get basic color information
        colors = self._get_dominant_colors(img)

        system = (
            "You are a product photography analyst for a premium e-commerce agency. "
            "Analyze this product image and describe:\n"
            "1. Product type identification\n"
            "2. Physical characteristics (shape, size, materials, colors)\n"
            "3. Current photography style (white background, lifestyle, etc.)\n"
            "4. Lighting assessment\n"
            "5. Composition assessment\n"
            "6. Quality assessment\n"
            "7. Suggestions for premium improvement\n\n"
            "Be specific and detailed. Output as JSON with keys: "
            "product_type, characteristics, current_style, lighting, "
            "composition, quality_score (1-10), premium_suggestions, colors_detected"
        )

        user = (
            f"Image: {width}x{height}px, format={format_name}, mode={mode}\n"
            f"Dominant colors: {colors}\n\n"
            "Describe this product image in detail for premium repositioning."
        )

        result = await self.claude.generate_text(system, user, temperature=0.3, max_tokens=1500)
        analysis = self._parse_json(result)
        analysis.update({
            "width": width,
            "height": height,
            "format": format_name,
            "dominant_colors": colors,
            "file_size": len(image_data),
        })
        return analysis

    async def analyze_multiple(self, images: list[bytes]) -> list[dict[str, Any]]:
        """Analyze multiple product images."""
        analyses = []
        for img_data in images:
            try:
                analysis = await self.analyze(img_data)
                analyses.append(analysis)
            except Exception as e:
                logger.error("image_analysis_failed", error=str(e))
                analyses.append({"error": str(e)})
        return analyses

    async def generate_image_brief(
        self,
        analyses: list[dict[str, Any]],
        product_info: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create a comprehensive image brief from analysis data."""
        system = (
            "You are a creative director for a premium European e-commerce brand. "
            "Based on the supplier image analysis and product info, create a detailed "
            "brief for generating premium marketing images.\n\n"
            "Describe the visual direction including: style, lighting, composition, "
            "color palette, mood, and specific elements to include."
        )
        user = f"Image Analysis: {analyses}\n"
        if product_info:
            user += f"Product Info: {product_info}\n"
        user += "\nCreate a comprehensive image generation brief for premium marketing visuals."

        return await self.claude.generate_text(system, user, temperature=0.6, max_tokens=2000)

    def _get_dominant_colors(self, img: Image.Image, num_colors: int = 5) -> list[str]:
        """Extract dominant colors from image."""
        try:
            # Resize for performance
            small = img.copy()
            small.thumbnail((100, 100))
            if small.mode != "RGB":
                small = small.convert("RGB")

            # Get colors via quantization
            palette = small.quantize(colors=num_colors)
            palette_img = palette.convert("RGB")
            color_count = {}
            for pixel in list(palette_img.getdata()):
                color_count[pixel] = color_count.get(pixel, 0) + 1

            sorted_colors = sorted(color_count.items(), key=lambda x: x[1], reverse=True)
            return [f"rgb({r},{g},{b})" for (r, g, b), _ in sorted_colors[:num_colors]]
        except Exception:
            return ["unknown"]

    def _parse_json(self, text: str) -> Any:
        import json
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
