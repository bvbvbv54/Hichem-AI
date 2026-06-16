from __future__ import annotations

from typing import Any, Optional

from services.claude.client import ClaudeClient
from services.claude.templates import PromptTemplate


class PromptEnhancer:
    """Orchestrates prompt enhancement using Claude and templates."""

    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def generate_from_template(
        self,
        template: PromptTemplate,
        parameters: dict[str, Any],
    ) -> str:
        filled = template.template.format(**parameters)
        result = await self.claude.generate_text(
            system_prompt=template.system_prompt,
            user_prompt=f"Create a detailed image prompt based on this structure:\n\n{filled}",
        )
        return result

    async def enhance_with_template(
        self,
        prompt: str,
        template: Optional[PromptTemplate] = None,
        style_guide: Optional[str] = None,
    ) -> str:
        return await self.claude.enhance_prompt(
            original_prompt=prompt,
            style_guide=style_guide,
        )

    async def full_pipeline(
        self,
        subject: str,
        template: Optional[PromptTemplate] = None,
        template_params: Optional[dict[str, Any]] = None,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        if template and template_params:
            raw = await self.generate_from_template(template, template_params)
        else:
            raw = await self.claude.generate_prompt(
                subject=subject,
                style=style,
                mood=mood,
                context=context,
            )
        return await self.claude.enhance_prompt(original_prompt=raw)
