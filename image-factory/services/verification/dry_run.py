from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from configs.settings import settings


@dataclass
class DryRunStep:
    step: str
    action: str
    estimated_cost_cents: int = 0
    estimated_duration_s: float = 0.0
    description: str = ""


@dataclass
class DryRunReport:
    steps: list[DryRunStep] = field(default_factory=list)
    total_estimated_cost_cents: int = 0
    total_estimated_duration_s: float = 0.0
    total_text_calls: int = 0
    total_image_calls: int = 0
    warnings: list[str] = field(default_factory=list)


class DryRunEngine:
    """Simulates the pipeline without consuming credits."""

    def preview_smoke_test(self) -> DryRunReport:
        steps = [
            DryRunStep(
                step="create_job",
                action="Create smoke test job record in PostgreSQL",
                estimated_cost_cents=0,
                estimated_duration_s=0.5,
                description="INSERT into jobs table, status=pending",
            ),
            DryRunStep(
                step="text_generation",
                action="Generate minimal test prompt via Claude",
                estimated_cost_cents=1,
                estimated_duration_s=2.0,
                description=f"1 text call to {settings.claude_model} with 50 token prompt",
            ),
            DryRunStep(
                step="image_generation",
                action="Generate 1 test image via provider",
                estimated_cost_cents=10,
                estimated_duration_s=5.0,
                description=f"1 image call to {settings.image_provider}, 256x256, 1 step",
            ),
            DryRunStep(
                step="storage",
                action="Store generated image to filesystem",
                estimated_cost_cents=0,
                estimated_duration_s=0.3,
                description="Write ~5KB PNG to outputs/",
            ),
            DryRunStep(
                step="delivery",
                action="Deliver asset to configured backends",
                estimated_cost_cents=0,
                estimated_duration_s=0.5,
                description=f"Deliver to {len(settings.delivery_backend_list)} backend(s)",
            ),
            DryRunStep(
                step="completion",
                action="Mark job completed, send SSE event",
                estimated_cost_cents=0,
                estimated_duration_s=0.2,
                description="UPDATE job status=completed, notify dashboard",
            ),
        ]

        total_cost = sum(s.estimated_cost_cents for s in steps)
        total_duration = sum(s.estimated_duration_s for s in steps)

        warnings = []
        if total_cost > 50:
            warnings.append(f"Estimated cost ${total_cost/100:.2f} exceeds $0.50 threshold")
        if settings.app_env == "production" and total_cost > 0:
            warnings.append("Running in production mode with non-zero cost")

        return DryRunReport(
            steps=steps,
            total_estimated_cost_cents=total_cost,
            total_estimated_duration_s=total_duration,
            total_text_calls=1,
            total_image_calls=1,
            warnings=warnings,
        )

    def preview_full_job(self) -> DryRunReport:
        steps = [
            DryRunStep("extract", "Extract product data from URL", 0, 3.0, "1 HTTP request to supplier page"),
            DryRunStep("translate", "Translate content (if needed)", 1, 1.0, "~100 token Claude call"),
            DryRunStep("reposition", "AI product repositioning", 3, 5.0, "~500 token Claude call"),
            DryRunStep("image_brief", "Generate image prompts", 2, 3.0, "~300 token Claude call"),
            DryRunStep("generate_1", "Generate hero image", 10, 5.0, "1x image generation"),
            DryRunStep("generate_2", "Generate lifestyle image", 10, 5.0, "1x image generation"),
            DryRunStep("generate_3", "Generate detail image", 10, 5.0, "1x image generation"),
            DryRunStep("generate_4", "Generate marketing banner", 10, 5.0, "1x image generation"),
            DryRunStep("store", "Store all assets", 0, 1.0, "4 files to storage"),
            DryRunStep("deliver", "Deliver all assets", 0, 2.0, "4 files to delivery backends"),
        ]
        total_cost = sum(s.estimated_cost_cents for s in steps)
        total_duration = sum(s.estimated_duration_s for s in steps)
        return DryRunReport(
            steps=steps,
            total_estimated_cost_cents=total_cost,
            total_estimated_duration_s=total_duration,
            total_text_calls=3,
            total_image_calls=4,
            warnings=[f"Full job estimated cost: ${total_cost/100:.2f}"] if total_cost > 50 else [],
        )
