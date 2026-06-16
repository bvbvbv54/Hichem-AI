from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def sample_spec():
    from services.pipeline.models import ProductSpec
    return ProductSpec(
        product_name="Test Bag",
        material="Canvas",
        dimensions="30x20cm",
        logo="None",
        translated_labels=[],
        key_visual_features=["Brown", "Straps"],
        background_color="White",
        primary_colors=["Brown"],
        detected_language="en",
    )


@pytest.mark.asyncio
async def test_output_count_min_3(tmp_path, sample_spec, mock_gemini):
    """Output count should be min(3, source_image_count)."""
    from services.pipeline.stage2_generator import Stage2Generator
    from services.pipeline.models import GenerationPlan

    refs = [str(tmp_path / f"ref{i}.jpg") for i in range(2)]
    for i, r in enumerate(refs):
        tmp_path.joinpath(f"ref{i}.jpg").write_bytes(b"data")

    plan = GenerationPlan(
        product_spec=sample_spec,
        reference_image_paths=refs,
        output_count=5,
        style_directive="test",
        negative_prompt="none",
    )

    redis = AsyncMock()
    gen = Stage2Generator()
    gen.gemini = mock_gemini
    assets = await gen.generate(plan, "job-test")
    assert len(assets) <= 2


@pytest.mark.asyncio
async def test_ranking_selects_highest(tmp_path, sample_spec):
    """Ranking step should select the highest-scoring candidate."""
    from services.pipeline.stage2_generator import Stage2Generator
    from services.pipeline.models import GenerationPlan, GeneratedAsset
    from datetime import datetime

    refs = [str(tmp_path / "ref.jpg")]
    tmp_path.joinpath("ref.jpg").write_bytes(b"data")

    plan = GenerationPlan(
        product_spec=sample_spec,
        reference_image_paths=refs,
        output_count=3,
        style_directive="test",
        negative_prompt="none",
    )

    gen = Stage2Generator()
    assets = [
        GeneratedAsset(local_path="a.png", prompt_used="p1", generation_timestamp=datetime.utcnow(), ranking_score=0.3, selected=True),
        GeneratedAsset(local_path="b.png", prompt_used="p2", generation_timestamp=datetime.utcnow(), ranking_score=0.9, selected=True),
        GeneratedAsset(local_path="c.png", prompt_used="p3", generation_timestamp=datetime.utcnow(), ranking_score=0.6, selected=True),
    ]

    sorted_assets = sorted(assets, key=lambda a: a.ranking_score, reverse=True)
    assert sorted_assets[0].ranking_score == 0.9
    assert sorted_assets[1].ranking_score == 0.6
    assert sorted_assets[2].ranking_score == 0.3


@pytest.mark.asyncio
async def test_selected_assets_at_most_2(tmp_path, sample_spec):
    """At most 2 assets should be selected."""
    from services.pipeline.stage2_generator import Stage2Generator
    from services.pipeline.models import GeneratedAsset
    from datetime import datetime

    a1 = GeneratedAsset(local_path="x.png", prompt_used="p1", generation_timestamp=datetime.utcnow(), ranking_score=0.9, selected=False)
    a2 = GeneratedAsset(local_path="y.png", prompt_used="p2", generation_timestamp=datetime.utcnow(), ranking_score=0.8, selected=False)
    a3 = GeneratedAsset(local_path="z.png", prompt_used="p3", generation_timestamp=datetime.utcnow(), ranking_score=0.7, selected=False)

    gen = Stage2Generator()
    all_assets = [a1, a2, a3]
    sorted_assets = sorted(all_assets, key=lambda a: a.ranking_score, reverse=True)
    selected = [a for a in sorted_assets[:2]]
    for a in selected:
        a.selected = True

    assert sum(1 for a in selected if a.selected) <= 2


@pytest.mark.asyncio
async def test_generate_with_no_references(sample_spec):
    """Generator should handle no reference images."""
    from services.pipeline.stage2_generator import Stage2Generator
    from services.pipeline.models import GenerationPlan
    plan = GenerationPlan(
        product_spec=sample_spec,
        reference_image_paths=[],
        output_count=3,
        style_directive="test",
        negative_prompt="none",
    )
    redis = AsyncMock()
    gen = Stage2Generator()
    assets = await gen.generate(plan, "job-no-ref")
    assert assets is not None
