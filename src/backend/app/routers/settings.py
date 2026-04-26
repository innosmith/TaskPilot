from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UserSettings(BaseModel):
    agenda_background_url: str | None = None
    agenda_background_type: str | None = None
    task_detail_mode: str | None = None
    sidebar_collapsed: bool | None = None
    app_logo_url: str | None = None
    sidebar_color: str | None = None


SETTINGS_FIELDS = [
    "agenda_background_url", "agenda_background_type", "task_detail_mode",
    "sidebar_collapsed", "app_logo_url", "sidebar_color",
]


@router.get("", response_model=UserSettings)
async def get_settings(
    user: User = Depends(get_current_user),
) -> UserSettings:
    s = user.settings or {}
    return UserSettings(**{f: s.get(f) for f in SETTINGS_FIELDS})


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
    return UserSettings(**{f: current.get(f) for f in SETTINGS_FIELDS})


# --- Triage-Einstellungen ---

class TriageSettings(BaseModel):
    triage_prompt: str | None = None
    triage_interval_seconds: int | None = None
    triage_enabled: bool | None = None


TRIAGE_FIELDS = ["triage_prompt", "triage_interval_seconds", "triage_enabled"]


@router.get("/triage", response_model=TriageSettings)
async def get_triage_settings(
    user: User = Depends(get_current_user),
) -> TriageSettings:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")
    s = user.settings or {}
    return TriageSettings(**{f: s.get(f) for f in TRIAGE_FIELDS})


@router.put("/triage", response_model=TriageSettings)
async def update_triage_settings(
    body: TriageSettings,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriageSettings:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")
    current = dict(user.settings or {})
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            current.pop(field, None)
        else:
            current[field] = value
    user.settings = current
    await db.flush()
    return TriageSettings(**{f: current.get(f) for f in TRIAGE_FIELDS})
