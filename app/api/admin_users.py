import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.config import settings
from app.models.user import USER_ROLES, User
from app.schemas.user import UserCreate, UserListOut, UserOut, UserRoleUpdate, UserStatusUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=UserListOut, summary="Lister les utilisateurs")
async def list_users(
    q: str | None = Query(None, description="Recherche par nom/email."),
    role: str | None = Query(None, pattern="^(admin|agent|readonly)$"),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(User.name.ilike(pattern) | User.email.ilike(pattern))
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    stmt = stmt.order_by(User.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return UserListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.post("", response_model=UserOut, status_code=201, summary="Creer un utilisateur")
async def create_user(
    body: UserCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    email = body.email.lower()
    if not email.endswith(f"@{settings.ADMIN_ALLOWED_DOMAIN}"):
        raise HTTPException(status_code=422, detail=f"Seuls les emails @{settings.ADMIN_ALLOWED_DOMAIN} sont autorises.")

    existing = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Un utilisateur avec cet email existe deja.")

    user = User(name=body.name.strip(), email=email, role=body.role, is_active=body.is_active)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/role", response_model=UserOut, summary="Mettre a jour le role")
async def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in USER_ROLES:
        raise HTTPException(status_code=422, detail=f"Role invalide. Valeurs autorisees: {USER_ROLES}")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if user.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer votre propre role admin.")

    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/status", response_model=UserOut, summary="Activer ou desactiver un utilisateur")
async def update_user_status(
    user_id: uuid.UUID,
    body: UserStatusUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if user.id == admin.id and not body.is_active:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas desactiver votre propre compte.")

    if user.role == "admin" and not body.is_active:
        active_admins = (
            await db.execute(
                select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
            )
        ).scalar_one()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="Impossible de desactiver le dernier admin actif.")

    user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    return user
