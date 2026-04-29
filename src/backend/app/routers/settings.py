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
    show_column_count: bool | None = None
    cockpit_background_url: str | None = None
    cockpit_background_type: str | None = None
    cockpit_calendar_exclude_categories: str | None = None
    cockpit_calendar_hide_private: bool | None = None
    inbox_background_url: str | None = None
    agents_background_url: str | None = None
    signale_background_url: str | None = None


SETTINGS_FIELDS = [
    "agenda_background_url", "agenda_background_type", "task_detail_mode",
    "sidebar_collapsed", "app_logo_url", "sidebar_color",
    "show_column_count", "cockpit_background_url", "cockpit_background_type",
    "cockpit_calendar_exclude_categories", "cockpit_calendar_hide_private",
    "inbox_background_url", "agents_background_url", "signale_background_url",
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


# --- Integrations-Einstellungen (Pipedrive etc.) ---

class IntegrationSettings(BaseModel):
    pipedrive_api_token: str | None = None
    pipedrive_domain: str | None = None
    toggl_api_token: str | None = None
    toggl_workspace_id: int | None = None
    bexio_api_token: str | None = None


INTEGRATION_FIELDS = ["pipedrive_api_token", "pipedrive_domain", "toggl_api_token", "toggl_workspace_id", "bexio_api_token"]


def _mask_token(token: str) -> str:
    if not token:
        return ""
    return f"{'*' * (len(token) - 4)}{token[-4:]}" if len(token) > 4 else "****"


@router.get("/integrations", response_model=IntegrationSettings)
async def get_integration_settings(
    user: User = Depends(get_current_user),
) -> IntegrationSettings:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")
    s = user.settings or {}
    return IntegrationSettings(
        pipedrive_api_token=_mask_token(s.get("pipedrive_api_token") or ""),
        pipedrive_domain=s.get("pipedrive_domain") or "innosmith",
        toggl_api_token=_mask_token(s.get("toggl_api_token") or ""),
        toggl_workspace_id=s.get("toggl_workspace_id"),
        bexio_api_token=_mask_token(s.get("bexio_api_token") or ""),
    )


@router.put("/integrations", response_model=IntegrationSettings)
async def update_integration_settings(
    body: IntegrationSettings,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationSettings:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")
    current = dict(user.settings or {})
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            current.pop(field, None)
        elif isinstance(value, str) and value.startswith("****"):
            pass
        elif isinstance(value, int):
            current[field] = value
        else:
            current[field] = value
    user.settings = current
    await db.flush()
    return IntegrationSettings(
        pipedrive_api_token=_mask_token(current.get("pipedrive_api_token") or ""),
        pipedrive_domain=current.get("pipedrive_domain") or "innosmith",
        toggl_api_token=_mask_token(current.get("toggl_api_token") or ""),
        toggl_workspace_id=current.get("toggl_workspace_id"),
        bexio_api_token=_mask_token(current.get("bexio_api_token") or ""),
    )
