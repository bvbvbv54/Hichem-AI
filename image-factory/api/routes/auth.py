from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.session import get_session
from api.dependencies import get_redis
from configs.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


SESSION_TTL = 7 * 24 * 3600  # 7 days

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    created_at: str | None = None


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, hash_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return dk.hex() == hash_hex
    except (ValueError, AttributeError):
        return False


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role or "user",
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session), redis=Depends(get_redis)):
    existing = await session.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        name=req.name,
        email=req.email,
        password_hash=_hash_password(req.password),
        role="admin",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = secrets.token_urlsafe(32)
    session_data = json.dumps({"user_id": user.id, "role": user.role})
    await redis.setex(f"session:{token}", SESSION_TTL, session_data)

    logger.info("user_registered", user_id=user.id, email=user.email)
    return AuthResponse(user=_user_to_response(user), token=token)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session), redis=Depends(get_redis)):
    result = await session.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    session_data = json.dumps({"user_id": user.id, "role": user.role})
    await redis.setex(f"session:{token}", SESSION_TTL, session_data)

    logger.info("user_logged_in", user_id=user.id, email=user.email)
    return AuthResponse(user=_user_to_response(user), token=token)


@router.post("/logout")
async def logout(redis=Depends(get_redis), authorization: str | None = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        await redis.delete(f"session:{token}")
    return {"status": "logged_out"}


@router.post("/refresh")
async def refresh_session(
    redis=Depends(get_redis),
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization[7:]
    session_data_raw = await redis.get(f"session:{token}")
    if not session_data_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    await redis.expire(f"session:{token}", SESSION_TTL)
    return {"status": "refreshed", "expires_in": SESSION_TTL}


@router.get("/me", response_model=UserResponse)
async def auth_me(
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
    authorization: str | None = Header(None),
):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.replace("Bearer ", "", 1) if authorization.startswith("Bearer ") else authorization
    session_data_raw = await redis.get(f"session:{token}")
    if not session_data_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    try:
        session_data = json.loads(session_data_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    result = await session.execute(select(User).where(User.id == session_data["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return _user_to_response(user)
