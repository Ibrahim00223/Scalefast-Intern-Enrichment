import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, hash_api_token
from app.config import settings
from app.models.api_token import APIToken
from app.models.user import User
from app.schemas.token import APITokenCreate, APITokenCreateOut, APITokenOut

router = APIRouter(prefix="/settings", tags=["settings"])


def _generate_api_token() -> str:
    return f"{settings.API_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


@router.get("/tokens", response_model=list[APITokenOut], summary="Lister mes tokens API")
async def list_my_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(APIToken)
        .where(APIToken.user_id == current_user.id)
        .order_by(APIToken.created_at.desc())
    )
    items = (await db.execute(stmt)).scalars().all()
    return list(items)


@router.post("/tokens", response_model=APITokenCreateOut, status_code=201, summary="Generer un token API")
async def create_api_token(
    body: APITokenCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    for _ in range(3):
        raw_token = _generate_api_token()
        token_hash = hash_api_token(raw_token)
        existing = (await db.execute(select(APIToken).where(APIToken.token_hash == token_hash))).scalar_one_or_none()
        if existing:
            continue

        token = APIToken(
            user_id=current_user.id,
            name=body.name.strip(),
            token_prefix=raw_token[:12],
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(token)
        await db.commit()
        return APITokenCreateOut(token=raw_token, token_prefix=token.token_prefix, expires_at=token.expires_at)

    raise HTTPException(status_code=500, detail="Impossible de generer un token unique.")


@router.delete("/tokens/{token_id}", status_code=204, summary="Revoquer un token API")
async def revoke_api_token(
    token_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = await db.get(APIToken, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token introuvable.")

    if token.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Action non autorisee.")

    token.is_active = False
    token.revoked_at = datetime.now(UTC)
    await db.commit()
