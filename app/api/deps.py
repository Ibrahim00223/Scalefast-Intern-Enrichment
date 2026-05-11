from typing import AsyncGenerator
from datetime import UTC, datetime

import hashlib
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.api_token import APIToken
from app.models.user import User


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def _decode_jwt_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide.") from exc


def hash_api_token(raw_token: str) -> str:
    payload = f"{settings.API_TOKEN_PEPPER}:{raw_token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def _get_user_from_api_token(db: AsyncSession, raw_token: str) -> User | None:
    token_hash = hash_api_token(raw_token)
    api_token = (await db.execute(select(APIToken).where(APIToken.token_hash == token_hash))).scalar_one_or_none()
    if not api_token:
        return None
    if not api_token.is_active or api_token.revoked_at is not None:
        return None
    if api_token.expires_at is not None and api_token.expires_at <= datetime.now(UTC):
        return None

    user = await db.get(User, api_token.user_id)
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
    access_token: str | None = Cookie(None),
) -> User:
    bearer_token = None
    if authorization:
        scheme, _, token_value = authorization.partition(" ")
        if scheme.lower() == "bearer" and token_value.strip():
            bearer_token = token_value.strip()

    if bearer_token:
        user = await _get_user_from_api_token(db, bearer_token)
        if user:
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API token invalide.")

    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise.")

    payload = _decode_jwt_token(access_token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide.")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide.")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Utilisateur non autorise.")

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acces admin requis.")
    return current_user


async def get_active_users_count(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
        )
    ).scalar_one()
