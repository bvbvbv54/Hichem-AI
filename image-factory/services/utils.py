from __future__ import annotations

import re


def sanitize_filename(name: str, max_length: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r'\s+', "_", name)
    return name.strip("._ ")[:max_length] or "product"
