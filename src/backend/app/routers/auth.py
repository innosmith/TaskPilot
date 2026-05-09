import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_owner
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import BoardMember, User
from app.schemas import LoginRequest, TokenOut, UserOut

logger = logging.getLogger("taskpilot.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()

_login_attempts: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 300
RATE_LIMIT_MAX = 10


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    attempts = _login_attempts[ip]
    _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Login-Versuche. Bitte warten.",
        )
    _login_attempts[ip].append(now)


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungueltige Anmeldedaten")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Konto deaktiviert")

    if user.mfa_enabled and user.mfa_secret:
        if not body.mfa_code:
            mfa_token = create_access_token(
                {"sub": str(user.id), "role": user.role, "mfa_pending": True},
                expires_delta=timedelta(minutes=5),
            )
            return JSONResponse(content={
                "requires_mfa": True,
                "mfa_token": mfa_token,
                "access_token": "",
                "token_type": "bearer",
            })

        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(body.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger MFA-Code",
            )

    user.last_login_at = datetime.now(timezone.utc)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role}, role=user.role)

    response = JSONResponse(content={
        "access_token": token,
        "token_type": "bearer",
        "requires_mfa": False,
        "mfa_token": None,
    })
    response.set_cookie(
        key="taskpilot_refresh",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.refresh_token_expire_hours * 3600,
        path="/api/auth/refresh",
    )
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return user


class ProfileUpdateBody(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None


@router.patch("/me", response_model=UserOut)
async def update_profile(
    body: ProfileUpdateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    return user


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Neues Passwort muss mindestens 8 Zeichen haben")
    user.password_hash = hash_password(body.new_password)
    await db.flush()
    return {"ok": True}


# --- MFA (TOTP) ---

class MfaVerifyBody(BaseModel):
    code: str


@router.post("/mfa/setup")
async def mfa_setup(
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generiert ein TOTP-Secret und gibt die Provisioning-URI zurueck."""
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    await db.flush()

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(user.email, issuer_name="TaskPilot")

    return {"secret": secret, "provisioning_uri": provisioning_uri}


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyBody,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verifiziert den TOTP-Code und aktiviert MFA."""
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA-Setup wurde noch nicht gestartet",
        )

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger TOTP-Code",
        )

    user.mfa_enabled = True
    await db.flush()
    logger.info("MFA aktiviert für User %s", user.email)
    return {"mfa_enabled": True}


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaVerifyBody,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deaktiviert MFA nach Verifikation des TOTP-Codes."""
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA ist nicht aktiviert",
        )

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger TOTP-Code",
        )

    user.mfa_enabled = False
    user.mfa_secret = None
    await db.flush()
    logger.info("MFA deaktiviert für User %s", user.email)
    return {"mfa_enabled": False}


# --- Refresh Token ---

@router.post("/refresh")
async def refresh_token(
    taskpilot_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Rotiert Refresh-Token und gibt neues Access-Token zurueck."""
    if not taskpilot_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kein Refresh-Token vorhanden",
        )

    payload = decode_refresh_token(taskpilot_refresh)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiges oder abgelaufenes Refresh-Token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiges Token-Payload",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden oder deaktiviert",
        )

    new_access = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh = create_refresh_token({"sub": str(user.id), "role": user.role}, role=user.role)

    response = JSONResponse(content={
        "access_token": new_access,
        "token_type": "bearer",
    })
    response.set_cookie(
        key="taskpilot_refresh",
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.refresh_token_expire_hours * 3600,
        path="/api/auth/refresh",
    )
    return response


class UserCreateBody(BaseModel):
    email: str
    display_name: str
    role: str = "member"
    password: str | None = None


class UserUpdateBody(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_owner),
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_owner),
) -> UserOut:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-Mail bereits registriert")

    temp_password = body.password or uuid.uuid4().hex[:12]
    user = User(
        email=body.email,
        password_hash=hash_password(temp_password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_owner),
) -> UserOut:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    return user


# --- Einladungs-Flow ---

class InviteBody(BaseModel):
    email: str
    project_id: str
    display_name: str | None = None


class InviteResult(BaseModel):
    user_id: str
    email: str
    project_id: str
    temp_password: str


@router.post("/invite", response_model=InviteResult, status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: InviteBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_owner),
) -> InviteResult:
    """Laedt einen Kunden als Member zu einem Projekt ein.
    Erstellt User (falls nötig) und board_members-Eintrag."""
    result = await db.execute(select(User).where(User.email == body.email))
    existing_user = result.scalar_one_or_none()

    temp_password = uuid.uuid4().hex[:12]

    if existing_user:
        member = existing_user
    else:
        display_name = body.display_name or body.email.split("@")[0]
        member = User(
            email=body.email,
            password_hash=hash_password(temp_password),
            display_name=display_name,
            role="member",
            invited_by=_user.id,
            must_change_password=True,
        )
        db.add(member)
        await db.flush()

    project_uuid = uuid.UUID(body.project_id)
    existing_bm = await db.execute(
        select(BoardMember).where(
            BoardMember.project_id == project_uuid,
            BoardMember.user_id == member.id,
        )
    )
    if not existing_bm.scalar_one_or_none():
        bm = BoardMember(
            project_id=project_uuid,
            user_id=member.id,
            role="member",
        )
        db.add(bm)

    await db.flush()
    logger.info("Member %s eingeladen zu Projekt %s", body.email, body.project_id)

    return InviteResult(
        user_id=str(member.id),
        email=body.email,
        project_id=body.project_id,
        temp_password=temp_password if not existing_user else "(bestehender User)",
    )


async def ensure_owner_exists(db: AsyncSession, retries: int = 5) -> None:
    settings = get_settings()
    for attempt in range(retries):
        try:
            result = await db.execute(select(User).where(User.role == "owner"))
            if result.scalar_one_or_none() is not None:
                return

            owner = User(
                email=settings.owner_email,
                password_hash=hash_password(settings.owner_password),
                display_name=settings.owner_display_name,
                role="owner",
            )
            db.add(owner)
            await db.commit()
            logger.info("Owner-User angelegt: %s", settings.owner_email)
            return
        except Exception:
            if attempt < retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "ensure_owner_exists fehlgeschlagen (Versuch %d/%d), Retry in %ds",
                    attempt + 1, retries, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.exception("ensure_owner_exists endgueltig fehlgeschlagen")
                raise
