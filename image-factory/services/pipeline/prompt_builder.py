from __future__ import annotations

from services.pipeline.models import GenerationPlan


class PromptBuilder:
    def build(self, plan: GenerationPlan) -> tuple[str, str]:
        spec = plan.product_spec
        labels_text = "\n".join(
            f'  - "{lbl.original}" → "{lbl.semantic_rewrite}"'
            for lbl in spec.translated_labels
        ) or "  None detected"
        features_text = "\n".join(f"  - {f}" for f in spec.key_visual_features)
        dimensions_line = f"Dimensions: {spec.dimensions}" if spec.dimensions else ""
        logo_line = f"Brand/Logo: {spec.logo}" if spec.logo else "Brand/Logo: None visible"

        positive = (
            f"Use the uploaded reference images ONLY as visual references for the product.\n"
            f"Create {plan.output_count} professional e-commerce product image(s) for the American market.\n"
            f"\n"
            f"Product: {spec.product_name}\n"
            f"Material: {spec.material}\n"
            f"{dimensions_line}\n"
            f"{logo_line}\n"
            f"\n"
            f"Maintain from reference images:\n"
            f"- Exact product shape and proportions\n"
            f"- All key visual features:\n"
            f"{features_text}\n"
            f"\n"
            f"Translated labels to include (in English only):\n"
            f"{labels_text}\n"
            f"\n"
            f"American e-commerce requirements:\n"
            f"- Clean white or light gray studio background\n"
            f"- Professional 3-point lighting with no harsh shadows on product\n"
            f"- All text and labels in English only — no Chinese characters\n"
            f"- Product centered and fills 70-80% of frame\n"
            f"- No lifestyle elements, no hands, no props unless in reference\n"
            f"\n"
            f"Do not invent any product features not visible in the reference images."
        )

        negative = (
            "chinese text, chinese characters, blurry, low resolution, watermark, "
            "distorted product, missing parts, extra objects, dark background, "
            "harsh shadows, busy background, lifestyle photography, props, hands, "
            "motion blur, overexposed, underexposed, logo changes"
        )
        return positive, negative
