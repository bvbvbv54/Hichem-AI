from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_claude_generate_prompt():
    from services.claude.client import ClaudeClient

    with patch.object(ClaudeClient, "generate_text", new_callable=AsyncMock) as mock:
        mock.return_value = "A premium lifestyle image of a modern living room."
        client = ClaudeClient()
        result = await client.generate_prompt(
            subject="modern sofa",
            style="scandinavian",
            mood="cozy",
        )
        assert "premium" in result.lower()
        assert mock.called


@pytest.mark.asyncio
async def test_claude_enhance_prompt():
    from services.claude.client import ClaudeClient

    with patch.object(ClaudeClient, "generate_text", new_callable=AsyncMock) as mock:
        mock.return_value = "Enhanced: A detailed product photo."
        client = ClaudeClient()
        result = await client.enhance_prompt("A product photo")
        assert "Enhanced" in result


@pytest.mark.asyncio
async def test_claude_translation():
    from services.translation.service import TranslationService
    from services.claude.client import ClaudeClient

    with patch.object(ClaudeClient, "generate_text", new_callable=AsyncMock) as mock:
        mock.return_value = "Hello, this is a product"
        claude = ClaudeClient()
        translator = TranslationService(claude)
        result = await translator.translate("Bonjour, ceci est un produit", "en")
        assert result == "Hello, this is a product"


@pytest.mark.asyncio
async def test_prompt_templates_exist():
    from services.claude.templates import ALL_TEMPLATES, list_templates

    templates = list_templates()
    assert len(templates) >= 10
    categories = {t["category"] for t in templates}
    assert "product_mockup" in categories
    assert "blog_thumbnail" in categories
    assert "landing_page" in categories


@pytest.mark.asyncio
async def test_product_repositioning():
    from services.repositioning.engine import ProductRepositioningEngine
    from services.claude.client import ClaudeClient

    with patch.object(ClaudeClient, "generate_text", new_callable=AsyncMock) as mock:
        mock.return_value = '{"brand_concept": "Premium Brand", "new_title": "Luxury Item"}'
        claude = ClaudeClient()
        engine = ProductRepositioningEngine(claude, None)
        result = await engine._analyze_product("Test Product", "A great product", "", None)
        assert "brand_concept" in result
