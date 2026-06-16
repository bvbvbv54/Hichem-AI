from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GenerationRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_images: int = 1
    model: str = ""
    seed: Optional[int] = None
    steps: int = 30
    guidance_scale: float = 7.5
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    image_data: bytes
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    seed: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
