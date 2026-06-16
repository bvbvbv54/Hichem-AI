from __future__ import annotations

import uuid
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from database.models.user import ApiKey
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


class CreateApiKeyRequest(BaseModel):
    name: str


@router.get("/api-keys")
async def list_api_keys(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ApiKey).limit(100))
    keys = result.scalars().all()
    return [
        {"id": k.id, "name": k.name, "key": k.key, "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None, "created_at": k.created_at.isoformat() if k.created_at else ""}
        for k in keys
    ]


@router.post("/api-keys")
async def create_api_key(req: CreateApiKeyRequest, session: AsyncSession = Depends(get_session)):
    key_value = f"if_{secrets.token_hex(24)}"
    api_key = ApiKey(id=str(uuid.uuid4()), user_id="default", name=req.name, key=key_value)
    session.add(api_key)
    await session.commit()
    logger.info("api_key_created", name=req.name)
    return {"id": api_key.id, "name": api_key.name, "key": key_value}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(ApiKey).where(ApiKey.id == key_id))
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"message": "API key deleted"}
