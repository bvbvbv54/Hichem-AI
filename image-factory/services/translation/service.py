from __future__ import annotations

from typing import Optional

from services.claude.client import ClaudeClient
from configs.logging import get_logger

logger = get_logger(__name__)


class TranslationService:
    """Handles multilingual content translation using Claude."""

    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def translate(self, text: str, target_language: str, source_language: Optional[str] = None) -> str:
        system = (
            f"You are a professional translator. Translate the following text to {target_language}. "
            "Preserve the original meaning, tone, and formatting. "
            "Output ONLY the translated text, no explanations."
        )
        prefix = f"Translate to {target_language}" + (f" from {source_language}" if source_language else "") + ":\n\n"
        return await self.claude.generate_text(system, f"{prefix}{text}", temperature=0.3)

    async def detect_and_translate(self, text: str, target_language: str = "en") -> tuple[str, str]:
        system = (
            "Detect the language of the following text and translate it to English. "
            "Respond in this format:\n"
            "SOURCE_LANGUAGE: <detected language>\n"
            "TRANSLATION: <translated text>"
        )
        result = await self.claude.generate_text(system, f"Translate:\n\n{text}", temperature=0.2)
        lines = result.split("\n")
        source_lang = "unknown"
        translation = text
        for line in lines:
            if line.startswith("SOURCE_LANGUAGE:"):
                source_lang = line.split(":", 1)[1].strip()
            elif line.startswith("TRANSLATION:"):
                translation = line.split(":", 1)[1].strip()
        return translation, source_lang
