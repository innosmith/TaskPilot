from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UserSettings(BaseModel):
    agenda_background_url: str | None = None
    agenda_background_type: str | None = None


@router.get("", response_model=UserSettings)
async def get_settings(
    user: User = Depends(get_current_user),
) -> UserSettings:
    s = user.settings or {}
    return UserSettings(
        agenda_background_url=s.get("agenda_background_url"),
        agenda_background_type=s.get("agenda_background_type"),
    )


@router.patch("", response_model=UserSettings)
async def update_settings(
    body: UserSettings,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettings:
    current = dict(user.settings or {})
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            current.pop(field, None)
        else:
            current[field] = value
    user.settings = current
    await db.flush()
    return UserSettings(
        agenda_background_url=current.get("agenda_background_url"),
        agenda_background_type=current.get("agenda_background_type"),
    )
