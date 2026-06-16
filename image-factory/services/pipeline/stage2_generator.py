from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from services.gemini.client import gemini_client
from services.nano_banana.client import NanoBananaClient
from services.pipeline.prompt_builder import PromptBuilder
from services.pipeline.models import GenerationPlan, GeneratedAsset
from services.pipeline.errors import PipelineError, ErrorCode, ErrorSeverity
from services.admin_notifier import get_notifier
from configs.logging import get_logger

logger = get_logger(__name__)

RANKING_PROMPT = """
You are a quality evaluator for American e-commerce product photography.
Rank the provided generated product images by their suitability for an American online store.

Evaluate each image on:
1. Product clarity — is the product clearly visible and in focus?
2. Background cleanliness — is the background clean (white or light gray preferred)?
3. Professional lighting — does it look like studio photography?
4. No unwanted text — are there any stray characters or labels that should not be there?
5. Visual appeal — would this image drive clicks on Amazon or Shopify?

Return ONLY a JSON array, no explanation:
[
  {"index": 0, "score": 0.92, "reason": "Clean white background, product centered"},
  {"index": 1, "score": 0.74, "reason": "Slight shadow on product edge"}
]

Score range: 0.0 (reject) to 1.0 (perfect). Any score below 0.4 should be considered unusable.
"""


class Stage2Generator:
    def __init__(self, output_dir: str = "outputs/generated") -> None:
        self._nano_banana = NanoBananaClient()
        self._prompt_builder = PromptBuilder()
        self._output_dir = Path(output_dir)

    async def generate(self, plan: GenerationPlan, job_id: str) -> list[GeneratedAsset]:
        notifier = get_notifier()
        output_count = min(3, len(plan.reference_image_paths))
        if output_count == 0:
            raise ValueError("No reference images available for generation")

        positive_prompt, negative_prompt = self._prompt_builder.build(plan)
        job_output_dir = self._output_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        candidates: list[GeneratedAsset] = []

        for i in range(output_count):
            try:
                image_bytes = await self._nano_banana.generate_image_to_image(
                    prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    reference_image_path=plan.reference_image_paths[0],
                    seed=i * 42,
                )
                candidate_path = str(job_output_dir / f"candidate_{i}.png")
                with open(candidate_path, "wb") as f:
                    f.write(image_bytes)
                candidates.append(GeneratedAsset(
                    local_path=candidate_path,
                    prompt_used=positive_prompt,
                    generation_timestamp=datetime.utcnow(),
                    ranking_score=0.0,
                    selected=False,
                ))
            except Exception as e:
                error_str = str(e).lower()
                if "quota" in error_str or "429" in error_str:
                    await notifier.notify(PipelineError(
                        code=ErrorCode.S2_NANOBANA_QUOTA,
                        severity=ErrorSeverity.ERROR,
                        message=f"Nano Banana quota exceeded on candidate {i+1} — remaining candidates skipped.",
                        technical_detail=str(e),
                        job_id=job_id,
                        stage="stage2_generation",
                        retryable=True,
                    ))
                    break
                else:
                    await notifier.notify(PipelineError(
                        code=ErrorCode.S2_NANOBANA_UNAVAILABLE,
                        severity=ErrorSeverity.WARNING,
                        message=f"Nano Banana image generation failed for candidate {i+1}/{output_count}. Continuing.",
                        technical_detail=str(e),
                        job_id=job_id,
                        stage="stage2_generation",
                        retryable=True,
                    ))
                    continue

        if not candidates:
            await notifier.notify(PipelineError(
                code=ErrorCode.S2_GENERATION_FAILED,
                severity=ErrorSeverity.ERROR,
                message="All image generation attempts failed for this product — job marked as failed.",
                job_id=job_id,
                stage="stage2_generation",
                retryable=True,
            ))
            raise RuntimeError("Stage 2: all generation candidates failed")

        # Ranking (non-fatal — if it fails, keep all candidates unranked)
        if len(candidates) > 1:
            try:
                candidates = await self._rank_candidates(candidates)
            except Exception as e:
                await notifier.notify(PipelineError(
                    code=ErrorCode.S2_RANKING_FAILED,
                    severity=ErrorSeverity.WARNING,
                    message="Gemini ranking call failed — all generated images will be kept unranked.",
                    technical_detail=str(e),
                    job_id=job_id,
                    stage="stage2_ranking",
                    retryable=False,
                ))
                for asset in candidates:
                    asset.ranking_score = 0.75
                    asset.selected = True

        keep_count = 1 if output_count == 1 else 2
        sorted_candidates = sorted(candidates, key=lambda a: a.ranking_score, reverse=True)
        for i, asset in enumerate(sorted_candidates):
            asset.selected = i < keep_count and asset.ranking_score >= 0.4

        usable = [a for a in candidates if a.selected]
        if not usable and len(candidates) > 0:
            scores = [a.ranking_score for a in candidates]
            await notifier.notify(PipelineError(
                code=ErrorCode.S2_ALL_BELOW_THRESHOLD,
                severity=ErrorSeverity.WARNING,
                message=f"All {len(candidates)} generated images scored below quality threshold (0.4). "
                        f"Best score: {max(scores):.2f}. Images saved — manual review recommended.",
                job_id=job_id,
                stage="stage2_ranking",
                retryable=True,
                context={"scores": scores},
            ))
            for asset in candidates:
                asset.selected = True

        logger.info("stage2_complete", job_id=job_id, generated=len(candidates), selected=sum(1 for a in candidates if a.selected))
        return candidates

    async def _rank_candidates(self, candidates: list[GeneratedAsset]) -> list[GeneratedAsset]:
        image_paths = [a.local_path for a in candidates]
        raw = await gemini_client.generate_with_images(RANKING_PROMPT, image_paths)
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        rankings = json.loads(cleaned)
        for r in rankings:
            idx = r["index"]
            if idx < len(candidates):
                candidates[idx].ranking_score = r["score"]
        return candidates
