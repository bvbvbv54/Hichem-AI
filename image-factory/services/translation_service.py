from __future__ import annotations

import re

import httpx

_ZH_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_JA_PATTERN = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
_KR_PATTERN = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_AR_PATTERN = re.compile(r"[\u0600-\u06ff]")
_RU_PATTERN = re.compile(r"[\u0400-\u04ff]")
_SCRIPT = re.compile(r"<[^>]+>", re.UNICODE)


def detect_language(text: str) -> str:
    if _ZH_PATTERN.search(text):
        return "zh"
    if _JA_PATTERN.search(text):
        return "ja"
    if _KR_PATTERN.search(text):
        return "ko"
    if _AR_PATTERN.search(text):
        return "ar"
    if _RU_PATTERN.search(text):
        return "ru"
    return "en"


def contains_chinese(text: str) -> bool:
    return bool(_ZH_PATTERN.search(text))


def needs_translation(text: str) -> bool:
    return detect_language(text) != "en"


async def translate_text(text: str, target: str = "en") -> str:
    if not text or not needs_translation(text):
        return text
    cleaned = _SCRIPT.sub("", text).strip()[:2000]
    if not cleaned:
        return text
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": cleaned},
            )
            resp.raise_for_status()
            data = resp.json()
            parts: list[str] = []
            for sentence in data[0]:
                if sentence and sentence[0]:
                    parts.append(sentence[0])
            return " ".join(parts) if parts else text
    except Exception:
        return text


async def batch_translate(texts: list[str], target_lang: str = "en") -> dict[str, str]:
    result: dict[str, str] = {}
    for t in texts:
        if t not in result:
            result[t] = await translate_text(t, target_lang)
    return result
