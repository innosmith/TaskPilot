from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
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


async def ensure_owner_exists(db: AsyncSession) -> None:
    """Erstellt den Owner-Account beim ersten Start, falls er nicht existiert."""
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
