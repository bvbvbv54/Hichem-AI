from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_semantic_translator_translates_labels():
    from services.pipeline.semantic_translator import SemanticTranslator
    translator = SemanticTranslator()

    with patch.object(translator, "translate_labels", new_callable=AsyncMock) as mock:
        mock.return_value = []
        result = await translator.translate_labels([])
        assert result == []


@pytest.mark.asyncio
async def test_semantic_translator_empty_input():
    from services.pipeline.semantic_translator import SemanticTranslator
    translator = SemanticTranslator()
    result = await translator.translate_labels([])
    assert result == []


@pytest.mark.asyncio
async def test_semantic_translator_returns_chinese_labels():
    from services.pipeline.semantic_translator import SemanticTranslator
    import services.pipeline.semantic_translator as st_mod

    translator = SemanticTranslator()

    fake_json = json.dumps([
        {"original": "真皮", "literal_translation": "Genuine leather", "semantic_rewrite": "Premium leather"},
        {"original": "中国制造", "literal_translation": "Made in China", "semantic_rewrite": "Made in China"},
    ])

    with patch.object(st_mod.gemini_client, "generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = fake_json
        labels = await translator.translate_labels([
            {"text": "真皮", "position": "front"},
            {"text": "中国制造", "position": "back"},
        ])

    assert len(labels) == 2
    assert labels[0].original == "真皮"
    assert labels[0].literal_translation == "Genuine leather"
    assert labels[0].position == "front"


@pytest.mark.asyncio
async def test_semantic_translator_handles_json_fence():
    from services.pipeline.semantic_translator import SemanticTranslator
    import services.pipeline.semantic_translator as st_mod

    translator = SemanticTranslator()

    fenced = "```json\n[{\"original\": \"测试\", \"literal_translation\": \"Test\", \"semantic_rewrite\": \"Test\"}]\n```"
    with patch.object(st_mod.gemini_client, "generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = fenced
        labels = await translator.translate_labels([{"text": "测试", "position": "center"}])

    assert len(labels) == 1
    assert labels[0].original == "测试"
