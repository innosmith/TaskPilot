import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_owner
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

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


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return user


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


async def ensure_owner_exists(db: AsyncSession) -> None:
    settings = get_settings()
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
