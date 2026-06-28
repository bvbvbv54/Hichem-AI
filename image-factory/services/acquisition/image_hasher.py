from __future__ import annotations

from pathlib import Path
from typing import Tuple

import imagehash
from PIL import Image

PHASH_SIMILARITY_THRESHOLD = 6  # hamming distance <= 6 means ~90%+ similar (64-bit hash)


def compute_phash(image_path: str | Path) -> imagehash.ImageHash | None:
    try:
        img = Image.open(image_path)
        return imagehash.phash(img)
    except Exception:
        return None


def compute_phash_from_bytes(data: bytes) -> imagehash.ImageHash | None:
    try:
        import io
        img = Image.open(io.BytesIO(data))
        return imagehash.phash(img)
    except Exception:
        return None


def is_similar(h1: imagehash.ImageHash, h2: imagehash.ImageHash, threshold: int = PHASH_SIMILARITY_THRESHOLD) -> bool:
    return (h1 - h2) <= threshold


def find_similar(hash_to_check: imagehash.ImageHash, existing_hashes: list[Tuple[imagehash.ImageHash, str]], threshold: int = PHASH_SIMILARITY_THRESHOLD) -> str | None:
    for existing_hash, identifier in existing_hashes:
        if (hash_to_check - existing_hash) <= threshold:
            return identifier
    return None
