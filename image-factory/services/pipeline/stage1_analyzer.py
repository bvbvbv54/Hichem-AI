from __future__ import annotations

import hashlib
import json

from google.api_core import exceptions as google_exceptions

from services.gemini.client import gemini_client
from services.pipeline.ocr_extractor import OCRExtractor
from services.pipeline.semantic_translator import SemanticTranslator
from services.pipeline.models import ProductSpec, ChineseLabel
from services.pipeline.errors import PipelineError, ErrorCode, ErrorSeverity
from services.admin_notifier import get_notifier
from configs.logging import get_logger

logger = get_logger(__name__)

ANALYSIS_PROMPT = """
You are analyzing a set of product images from the same supplier listing.
These images show the same product from different angles or with different details.

Analyze ALL images together as a unified product and return a single JSON object.
Do NOT generate any new images. Only analyze what you can see.

Return ONLY valid JSON with no explanation:
{
  "product_name": "<concise English product name, 3-6 words>",
  "material": "<primary material visible in images>",
  "dimensions": "<if any dimension is shown, e.g. '30cm x 20cm', otherwise null>",
  "logo": "<brand name or logo text visible in images, otherwise null>",
  "key_visual_features": [
    "<distinct feature 1>",
    "<distinct feature 2>"
  ],
  "background_color": "<dominant background: white | light-gray | gradient | lifestyle | colored>",
  "primary_colors": ["<main product color 1>", "<main product color 2>"]
}

Rules:
- product_name must be in English regardless of language in images
- Do not invent features not visible in the images
- key_visual_features should describe what makes this product distinct (shape, finish, attachments)
"""


class Stage1Analyzer:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._ocr = OCRExtractor(redis_client)
        self._translator = SemanticTranslator()

    async def analyze(self, image_paths: list[str], product_url: str) -> ProductSpec:
        notifier = get_notifier()
        url_hash = hashlib.md5(product_url.encode()).hexdigest()
        cache_key = f"stage1:result:{url_hash}"
        cached = await self._redis.get(cache_key)
        if cached:
            logger.info("stage1_cache_hit", url=product_url)
            return self._deserialize(json.loads(cached))

        all_chinese_labels = []
        translated_labels: list[ChineseLabel] = []

        # OCR (non-fatal — if it fails, continue without translation)
        try:
            ocr_results = await self._ocr.scan_all(image_paths)
            for result in ocr_results:
                if result.get("has_chinese"):
                    all_chinese_labels.extend(result.get("labels", []))
        except json.JSONDecodeError as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.OCR_PARSE_FAILED,
                severity=ErrorSeverity.WARNING,
                message="OCR response was not valid JSON — skipping Chinese label detection for this product.",
                technical_detail=str(e),
                stage="ocr_extraction",
                product_url=product_url,
                retryable=False,
            ))
        except google_exceptions.ResourceExhausted as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.OCR_GEMINI_QUOTA,
                severity=ErrorSeverity.ERROR,
                message="Gemini API quota exceeded during OCR scan. Processing paused — will retry in 60 seconds.",
                technical_detail=str(e),
                stage="ocr_extraction",
                product_url=product_url,
                retryable=True,
            ))
            raise
        except Exception as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.OCR_GEMINI_UNAVAILABLE,
                severity=ErrorSeverity.WARNING,
                message=f"OCR scan failed unexpectedly — continuing without label detection.",
                technical_detail=str(e),
                stage="ocr_extraction",
                product_url=product_url,
                retryable=False,
            ))

        # Translation (non-fatal — if it fails, keep literal labels or skip)
        if all_chinese_labels:
            try:
                translated_labels = await self._translator.translate_labels(all_chinese_labels)
            except json.JSONDecodeError as e:
                await notifier.notify(PipelineError(
                    code=ErrorCode.TRANS_FAILED,
                    severity=ErrorSeverity.WARNING,
                    message="Semantic translation returned malformed response — Chinese labels will be skipped.",
                    technical_detail=str(e),
                    stage="semantic_translation",
                    product_url=product_url,
                    retryable=False,
                ))
            except google_exceptions.ResourceExhausted as e:
                await notifier.notify(PipelineError(
                    code=ErrorCode.S1_GEMINI_QUOTA,
                    severity=ErrorSeverity.ERROR,
                    message="Gemini quota exceeded during translation — retrying job.",
                    technical_detail=str(e),
                    stage="semantic_translation",
                    product_url=product_url,
                    retryable=True,
                ))
                raise
            except Exception as e:
                await notifier.notify(PipelineError(
                    code=ErrorCode.OCR_GEMINI_UNAVAILABLE,
                    severity=ErrorSeverity.WARNING,
                    message="Translation failed unexpectedly — continuing without translated labels.",
                    technical_detail=str(e),
                    stage="semantic_translation",
                    product_url=product_url,
                    retryable=False,
                ))

        # Main Gemini Vision call (FATAL if this fails)
        analysis = None
        try:
            raw = await gemini_client.generate_with_images(ANALYSIS_PROMPT, image_paths)
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            analysis = json.loads(cleaned)
        except json.JSONDecodeError as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.S1_PARSE_FAILED,
                severity=ErrorSeverity.ERROR,
                message="Gemini returned a non-JSON product analysis — cannot build ProductSpec. Job will be retried.",
                technical_detail=f"Raw: {raw[:300] if 'raw' in dir() else 'unknown'}...",
                stage="stage1_analysis",
                product_url=product_url,
                retryable=True,
            ))
            raise ValueError(f"Stage 1 JSON parse failed: {e}") from e
        except google_exceptions.ResourceExhausted as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.S1_GEMINI_QUOTA,
                severity=ErrorSeverity.ERROR,
                message="Gemini API quota exceeded during product analysis — job queued for retry.",
                technical_detail=str(e),
                stage="stage1_analysis",
                product_url=product_url,
                retryable=True,
            ))
            raise
        except google_exceptions.ServiceUnavailable as e:
            await notifier.notify(PipelineError(
                code=ErrorCode.S1_GEMINI_UNAVAILABLE,
                severity=ErrorSeverity.ERROR,
                message="Gemini API is temporarily unavailable — job will be retried automatically.",
                technical_detail=str(e),
                stage="stage1_analysis",
                product_url=product_url,
                retryable=True,
            ))
            raise

        detected_language = "chinese" if all_chinese_labels else "none"
        spec = ProductSpec(
            product_name=analysis.get("product_name", "Unknown Product"),
            material=analysis.get("material", ""),
            dimensions=analysis.get("dimensions"),
            logo=analysis.get("logo"),
            translated_labels=translated_labels,
            key_visual_features=analysis.get("key_visual_features", []),
            background_color=analysis.get("background_color", "white"),
            primary_colors=analysis.get("primary_colors", []),
            detected_language=detected_language,
        )

        await self._redis.setex(cache_key, 3600, json.dumps(self._serialize(spec)))
        logger.info("stage1_complete", product=spec.product_name, had_chinese=bool(all_chinese_labels))
        return spec

    @staticmethod
    def _serialize(spec: ProductSpec) -> dict:
        import dataclasses
        return dataclasses.asdict(spec)

    @staticmethod
    def _deserialize(d: dict) -> ProductSpec:
        labels_data = d.pop("translated_labels", [])
        labels = [ChineseLabel(**lbl) for lbl in labels_data]
        return ProductSpec(**d, translated_labels=labels)
