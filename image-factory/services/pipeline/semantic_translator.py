from __future__ import annotations

import json

from services.gemini.client import gemini_client
from services.pipeline.models import ChineseLabel
from configs.logging import get_logger

logger = get_logger(__name__)

TRANSLATION_PROMPT = """
You are an expert American e-commerce product copywriter.
You receive Chinese product labels extracted via OCR from supplier product images.

For each label, produce TWO versions:
1. literal_translation: the closest English translation of the words
2. semantic_rewrite: the benefit-oriented American marketing language

Rules for semantic_rewrite:
- Must sound natural to an American consumer buying online
- Prefer benefit language over technical specs
- Maximum 4 words
- Never use Chinese-market phrasing or direct translations
- Preserve brand names and model numbers unchanged
- If the label is a spec (e.g. "2000mAh"), keep it as-is

Examples:
  超强吸附    → literal: "Super strong adsorption"      → semantic: "Powerful grip"
  防水涂层    → literal: "Waterproof coating"            → semantic: "Weather-resistant finish"
  环保材料    → literal: "Eco-friendly materials"        → semantic: "Sustainable materials"
  超轻量化    → literal: "Ultra lightweight"              → semantic: "Featherlight design"

Input is a JSON array of detected labels. Return ONLY a JSON array, no explanation:
[
  {
    "original": "...",
    "literal_translation": "...",
    "semantic_rewrite": "..."
  }
]
"""


class SemanticTranslator:
    async def translate_labels(self, ocr_labels: list[dict]) -> list[ChineseLabel]:
        if not ocr_labels:
            return []
        input_payload = [
            {"original": lbl["text"], "context": lbl.get("context", "")}
            for lbl in ocr_labels
        ]
        prompt = TRANSLATION_PROMPT + "\n\nInput:\n" + json.dumps(input_payload, ensure_ascii=False)
        raw = await gemini_client.generate_text(prompt, temperature=0.3)
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        translated = json.loads(cleaned)
        result = []
        for i, t in enumerate(translated):
            position = ocr_labels[i].get("position", "unknown") if i < len(ocr_labels) else "unknown"
            result.append(ChineseLabel(
                original=t["original"],
                literal_translation=t["literal_translation"],
                semantic_rewrite=t["semantic_rewrite"],
                position=position,
            ))
        return result
