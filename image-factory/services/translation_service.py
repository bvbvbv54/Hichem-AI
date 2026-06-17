from __future__ import annotations

import asyncio
import re

from configs.logging import get_logger

logger = get_logger(__name__)

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+")
_RESULT_RE = re.compile(r'class="result-container">([^<]+)')
_translation_cache: dict[str, str] = {}


def contains_chinese(text: str) -> bool:
    return bool(_CHINESE_RE.search(text))


def _translate_sync(text: str, target_lang: str = "en") -> str:
    import httpx
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(
                "https://translate.google.com/m",
                params={"sl": "zh-CN", "tl": target_lang, "q": text},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            if resp.status_code == 200:
                match = _RESULT_RE.search(resp.text)
                if match:
                    return match.group(1).strip()
    except Exception as e:
        logger.warning("translation_failed", error=str(e), text=text[:50])
    return text


async def translate_text(text: str, target_lang: str = "en") -> str:
    if not contains_chinese(text):
        return text
    cached = _translation_cache.get(text)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(_translate_sync, text, target_lang)
    _translation_cache[text] = result
    return result


async def batch_translate(texts: list[str], target_lang: str = "en") -> dict[str, str]:
    needed = []
    result_map = {}
    for t in texts:
        if not t:
            result_map[t] = t
            continue
        if not contains_chinese(t):
            result_map[t] = t
            continue
        cached = _translation_cache.get(t)
        if cached is not None:
            result_map[t] = cached
        else:
            needed.append(t)

    if needed:
        sem = asyncio.Semaphore(5)

        async def translate_one(t: str) -> str:
            async with sem:
                return await asyncio.to_thread(_translate_sync, t, target_lang)

        translations = await asyncio.gather(*[translate_one(t) for t in needed])
        for t, translated in zip(needed, translations):
            _translation_cache[t] = translated
            result_map[t] = translated

    return result_map
