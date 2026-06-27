from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

PROMPT_TEMPLATES = {
    "product_shot": {
        "name": "Product Shot",
        "category": "product",
        "description": "Professional white-background product photography",
        "default_parameters": {},
    },
    "lifestyle": {
        "name": "Lifestyle",
        "category": "product",
        "description": "Product in use lifestyle imagery",
        "default_parameters": {},
    },
}

router = APIRouter()


@router.get("/templates", summary="List all prompt templates")
async def get_templates(category: Optional[str] = None):
    if category:
        return {"templates": {k: v for k, v in PROMPT_TEMPLATES.items() if v.get("category") == category}}
    return {"templates": PROMPT_TEMPLATES}


@router.get("/templates/{name}", summary="Get template details")
async def get_template(name: str):
    template = PROMPT_TEMPLATES.get(name)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return template
