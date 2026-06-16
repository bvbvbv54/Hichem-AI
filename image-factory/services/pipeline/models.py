from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChineseLabel:
    original: str
    literal_translation: str
    semantic_rewrite: str
    position: str


@dataclass
class ProductSpec:
    product_name: str
    material: str
    dimensions: str
    logo: str
    translated_labels: list[ChineseLabel]
    key_visual_features: list[str]
    background_color: str
    primary_colors: list[str]
    detected_language: str


@dataclass
class GenerationPlan:
    product_spec: ProductSpec
    reference_image_paths: list[str]
    output_count: int
    style_directive: str
    negative_prompt: str


@dataclass
class GeneratedAsset:
    local_path: str
    prompt_used: str
    generation_timestamp: datetime
    ranking_score: float
    selected: bool


@dataclass
class PipelineResult:
    job_id: str
    product_url: str
    product_spec: ProductSpec
    reference_images: list[str]
    generated_assets: list[GeneratedAsset]
    selected_assets: list[str]
    had_chinese_labels: bool
    processing_duration_s: float
    error: str | None = None
