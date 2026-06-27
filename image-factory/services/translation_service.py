from __future__ import annotations

from typing import Any


def contains_chinese(text: str) -> bool:
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False


async def batch_translate(texts: list[str], target_lang: str = "en") -> dict[str, str]:
    return {t: t for t in texts}
