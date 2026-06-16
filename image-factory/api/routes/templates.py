from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from services.claude.templates import list_templates, ALL_TEMPLATES

router = APIRouter()


@router.get("/templates", summary="List all prompt templates")
async def get_templates(category: Optional[str] = None):
    return {"templates": list_templates(category)}


@router.get("/templates/{name}", summary="Get template details")
async def get_template(name: str):
    template = ALL_TEMPLATES.get(name)
    if not template:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return {
        "name": template.name,
        "category": template.category.value,
        "description": template.description,
        "default_parameters": template.default_parameters,
        "suggested_aspect_ratio": template.suggested_aspect_ratio,
        "suggested_style": template.suggested_style,
    }
