import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import jwt
import requests
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_google_auth_url(state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def _create_jwt(user: User, token_type: str) -> str:
    now = datetime.now(UTC)
    if token_type == "access":
        expires = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    else:
        expires = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _set_auth_cookies(response: Response, user: User) -> None:
    access = _create_jwt(user, "access")
    refresh = _create_jwt(user, "refresh")
    secure = settings.APP_BASE_URL.startswith("https://")

    response.set_cookie(
        key="access_token",
        value=access,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("oauth_state", path="/")


@router.get("/google/login", summary="Lancer la connexion Google")
async def google_login():
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth non configure.")

    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=_build_google_auth_url(state), status_code=302)
    secure = settings.APP_BASE_URL.startswith("https://")
    response.set_cookie("oauth_state", state, httponly=True, secure=secure, samesite="lax", max_age=600, path="/")
    return response


@router.get("/google/callback", summary="Callback Google OAuth")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Etat OAuth invalide.")

    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if token_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Echec de l'authentification Google.")

    token_data = token_res.json()
    raw_id_token = token_data.get("id_token")
    if not raw_id_token:
        raise HTTPException(status_code=401, detail="Token Google manquant.")

    try:
        info = id_token.verify_oauth2_token(raw_id_token, Request(), settings.GOOGLE_CLIENT_ID)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token Google invalide.") from exc

    email = str(info.get("email", "")).strip().lower()
    google_sub = str(info.get("sub", "")).strip()
    name = str(info.get("name") or email.split("@")[0]).strip()
    email_verified = bool(info.get("email_verified", False))

    if not email_verified or not email.endswith(f"@{settings.ADMIN_ALLOWED_DOMAIN}"):
        raise HTTPException(status_code=403, detail="Acces refuse pour ce domaine email.")

    user = None
    if google_sub:
        user = (await db.execute(select(User).where(User.google_sub == google_sub))).scalar_one_or_none()
    if not user:
        user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()

    if not user:
        total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        role = "readonly"
        is_bootstrap = settings.ADMIN_BOOTSTRAP_EMAIL and email == settings.ADMIN_BOOTSTRAP_EMAIL.lower()
        if total_users == 0 and (is_bootstrap or settings.ADMIN_BOOTSTRAP_EMAIL is None):
            role = "admin"
        user = User(name=name, email=email, google_sub=google_sub or None, role=role, is_active=True)
        db.add(user)
    else:
        user.name = name or user.name
        user.email = email
        if google_sub:
            user.google_sub = google_sub

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Utilisateur desactive.")

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    response = RedirectResponse(url="/", status_code=302)
    _set_auth_cookies(response, user)
    response.delete_cookie("oauth_state", path="/")
    return response


@router.get("/me", response_model=UserOut, summary="Profil utilisateur courant")
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh", summary="Rafraichir les tokens")
async def refresh_tokens(
    response: Response,
    refresh_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token manquant.")

    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Refresh token invalide.") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token invalide.")

    user_id = payload.get("sub")
    user = await db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Utilisateur non autorise.")

    _set_auth_cookies(response, user)
    return {"ok": True}


@router.post("/logout", summary="Se deconnecter")
async def logout(response: Response):
    _clear_auth_cookies(response)
    return {"ok": True}
