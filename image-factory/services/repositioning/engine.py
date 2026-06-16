from __future__ import annotations

import json
from typing import Any, Optional

from services.claude.client import ClaudeClient
from services.translation.service import TranslationService
from configs.logging import get_logger

logger = get_logger(__name__)


class ProductRepositioningEngine:
    """
    AI-powered product repositioning for premium European market presentation.
    Transforms supplier product data into premium brand-ready content.
    """

    def __init__(self, claude: ClaudeClient, translator: TranslationService) -> None:
        self.claude = claude
        self.translator = translator

    async def reposition(
        self,
        title: str,
        description: str,
        category: str = "",
        images_analysis: Optional[str] = None,
        target_market: str = "European premium e-commerce",
        language: str = "en",
    ) -> dict[str, Any]:
        # Ensure content is in English for processing
        if language != "en":
            title, _ = await self.translator.detect_and_translate(title)
            description, _ = await self.translator.detect_and_translate(description)

        product_analysis = await self._analyze_product(title, description, category, images_analysis)
        positioning = await self._create_positioning(product_analysis, target_market)
        marketing_copy = await self._generate_marketing_copy(positioning)
        image_briefs = await self._generate_image_briefs(positioning, images_analysis)

        return {
            "product_analysis": product_analysis,
            "positioning": positioning,
            "marketing_copy": marketing_copy,
            "image_briefs": image_briefs,
        }

    async def _analyze_product(
        self,
        title: str,
        description: str,
        category: str,
        images_analysis: Optional[str],
    ) -> dict[str, Any]:
        system = (
            "You are a product analyst for a premium European e-commerce agency. "
            "Analyze the following supplier product and identify: "
            "1. Core product type and category\n"
            "2. Key features and specifications\n"
            "3. Materials and quality indicators\n"
            "4. Target usage context\n"
            "5. Design aesthetic\n"
            "6. Competitor positioning opportunities\n"
            "7. Premium angles that can be emphasized\n\n"
            "Output as JSON with keys: core_product, key_features, materials, "
            "usage_context, design_aesthetic, premium_angles, target_audience"
        )
        user = f"Title: {title}\nDescription: {description}\nCategory: {category}\n"
        if images_analysis:
            user += f"Image Analysis: {images_analysis}\n"

        result = await self.claude.generate_text(system, user, temperature=0.4, max_tokens=2000)
        return self._parse_json(result)

    async def _create_positioning(
        self,
        analysis: dict[str, Any],
        target_market: str,
    ) -> dict[str, Any]:
        system = (
            "You are a brand strategist specializing in European market positioning. "
            f"Transform this product analysis into a premium {target_market} brand concept. "
            "Create a positioning that feels like a premium European brand, not a resold supplier product. "
            "Never mention China, factories, Alibaba, AliExpress, or wholesale suppliers.\n\n"
            "Output as JSON with keys: brand_concept, new_title, tagline, "
            "unique_selling_points, brand_story, target_audience_description"
        )
        result = await self.claude.generate_text(
            system,
            json.dumps(analysis, indent=2),
            temperature=0.7,
            max_tokens=2000,
        )
        return self._parse_json(result)

    async def _generate_marketing_copy(self, positioning: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You are a copywriter for premium European brands. "
            "Create compelling marketing copy based on the product positioning.\n\n"
            "Output as JSON with keys: "
            "product_title (premium version), "
            "short_description (2-3 sentences), "
            "long_description (2-3 paragraphs), "
            "key_features (list of 5-7 premium features as bullet points), "
            "selling_points (list of 3-5 unique selling propositions), "
            "seo_keywords (list of 10-15 keywords)"
        )
        result = await self.claude.generate_text(
            system,
            json.dumps(positioning, indent=2),
            temperature=0.6,
            max_tokens=3000,
        )
        return self._parse_json(result)

    async def _generate_image_briefs(
        self,
        positioning: dict[str, Any],
        images_analysis: Optional[str],
    ) -> list[dict[str, Any]]:
        system = (
            "You are a creative director for a premium e-commerce brand. "
            "Create detailed image generation briefs for the following product positioning. "
            "Each brief should describe a specific type of marketing image.\n\n"
            "Generate briefs for: "
            "1. Hero image - main product showcase\n"
            "2. Lifestyle image - product in premium context\n"
            "3. Detail image - product feature focus\n"
            "4. Marketing banner - campaign ready\n\n"
            "Output as JSON array. Each brief has keys: "
            "type, prompt, style, mood, composition, lighting, color_palette, aspect_ratio"
        )
        user = json.dumps(positioning, indent=2)
        if images_analysis:
            user += f"\n\nReference from supplier images: {images_analysis}"

        result = await self.claude.generate_text(system, user, temperature=0.7, max_tokens=3000)
        return self._parse_json(result) if isinstance(self._parse_json(result), list) else [self._parse_json(result)]

    def _parse_json(self, text: str) -> Any:
        # Try to extract JSON from the response
        text = text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last line if they're fences
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("json_parse_failed, returning raw text")
            return {"raw": text}
