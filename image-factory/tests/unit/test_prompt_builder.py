from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_prompt_builder_basic():
    from services.pipeline.prompt_builder import PromptBuilder
    from services.pipeline.models import ProductSpec, ChineseLabel, GenerationPlan
    spec = ProductSpec(
        product_name="Handbag",
        material="Leather",
        dimensions="30x20x10cm",
        logo="None",
        translated_labels=[
            ChineseLabel(original="真皮", literal_translation="Genuine leather", semantic_rewrite="Premium leather", position="front"),
        ],
        key_visual_features=["Brown color", "Gold buckle"],
        background_color="White",
        primary_colors=["Brown", "Gold"],
        detected_language="zh",
    )
    plan = GenerationPlan(
        product_spec=spec,
        reference_image_paths=[],
        output_count=3,
        style_directive="American e-commerce, studio lighting",
        negative_prompt="low quality, watermark",
    )
    builder = PromptBuilder()
    prompt, negative = builder.build(plan)
    assert "Handbag" in prompt
    assert "Leather" in prompt
    assert "American e-commerce" in prompt


@pytest.mark.asyncio
async def test_prompt_builder_no_chinese():
    from services.pipeline.prompt_builder import PromptBuilder
    from services.pipeline.models import ProductSpec, GenerationPlan
    spec = ProductSpec(
        product_name="Shoe", material="Cotton", dimensions="10x10x5",
        logo="Nike", translated_labels=[], key_visual_features=["White"],
        background_color="Gray", primary_colors=["White"], detected_language="en",
    )
    plan = GenerationPlan(
        product_spec=spec, reference_image_paths=[], output_count=3,
        style_directive="Minimalist style", negative_prompt="none",
    )
    builder = PromptBuilder()
    prompt, negative = builder.build(plan)
    assert "Shoe" in prompt


@pytest.mark.asyncio
async def test_prompt_builder_negative_prompt():
    from services.pipeline.prompt_builder import PromptBuilder
    from services.pipeline.models import ProductSpec, GenerationPlan
    spec = ProductSpec(
        product_name="Hat", material="Wool", dimensions="20x20x10",
        logo="", translated_labels=[], key_visual_features=["Blue"],
        background_color="White", primary_colors=["Blue"], detected_language="en",
    )
    plan = GenerationPlan(
        product_spec=spec, reference_image_paths=[], output_count=3,
        style_directive="test", negative_prompt="low quality, watermark",
    )
    builder = PromptBuilder()
    prompt, negative = builder.build(plan)
    assert "watermark" in negative


@pytest.mark.asyncio
async def test_prompt_builder_empty_spec():
    from services.pipeline.prompt_builder import PromptBuilder
    from services.pipeline.models import ProductSpec, GenerationPlan
    spec = ProductSpec(
        product_name="", material="", dimensions="",
        logo="", translated_labels=[], key_visual_features=[],
        background_color="", primary_colors=[], detected_language="",
    )
    plan = GenerationPlan(
        product_spec=spec, reference_image_paths=[], output_count=1,
        style_directive="Standard", negative_prompt="none",
    )
    builder = PromptBuilder()
    prompt, negative = builder.build(plan)
    assert isinstance(prompt, str)
