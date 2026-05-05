import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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
    finance_background_url: str | None = None
    debtors_background_url: str | None = None
    creditors_background_url: str | None = None
    chat_background_url: str | None = None
    debtor_budgets: dict | None = None


SETTINGS_FIELDS = [
    "agenda_background_url", "agenda_background_type", "task_detail_mode",
    "sidebar_collapsed", "app_logo_url", "sidebar_color",
    "show_column_count", "cockpit_background_url", "cockpit_background_type",
    "cockpit_calendar_exclude_categories", "cockpit_calendar_hide_private",
    "inbox_background_url", "agents_background_url", "signale_background_url",
    "finance_background_url", "debtors_background_url", "creditors_background_url",
    "chat_background_url", "debtor_budgets",
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
    flag_modified(user, "settings")
    await db.flush()
    return UserSettings(**{f: current.get(f) for f in SETTINGS_FIELDS})


# --- Triage-Einstellungen ---

class TriageSettings(BaseModel):
    triage_prompt: str | None = None
    triage_interval_seconds: int | None = None
    triage_enabled: bool | None = None
    inbox_hidden_folders: list[str] | None = None


TRIAGE_FIELDS = ["triage_prompt", "triage_interval_seconds", "triage_enabled", "inbox_hidden_folders"]


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
    flag_modified(user, "settings")
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
    flag_modified(user, "settings")
    await db.flush()
    return IntegrationSettings(
        pipedrive_api_token=_mask_token(current.get("pipedrive_api_token") or ""),
        pipedrive_domain=current.get("pipedrive_domain") or "innosmith",
        toggl_api_token=_mask_token(current.get("toggl_api_token") or ""),
        toggl_workspace_id=current.get("toggl_workspace_id"),
        bexio_api_token=_mask_token(current.get("bexio_api_token") or ""),
    )


# --- LLM-Einstellungen ---

class LlmProviderConfig(BaseModel):
    enabled: bool = False
    models: list[str] = []


class LlmSettingsPayload(BaseModel):
    llm_providers: dict[str, LlmProviderConfig] | None = None
    llm_default_model: str | None = None
    llm_default_local_model: str | None = None
    llm_default_temperature: float | None = None


LLM_FIELDS = ["llm_providers", "llm_default_model", "llm_default_local_model", "llm_default_temperature"]


@router.get("/llm", response_model=LlmSettingsPayload)
async def get_llm_settings(
    user: User = Depends(get_current_user),
) -> LlmSettingsPayload:
    s = user.settings or {}
    raw_providers = s.get("llm_providers")
    providers = None
    if raw_providers and isinstance(raw_providers, dict):
        providers = {
            k: LlmProviderConfig(**v) if isinstance(v, dict) else v
            for k, v in raw_providers.items()
        }
    return LlmSettingsPayload(
        llm_providers=providers,
        llm_default_model=s.get("llm_default_model"),
        llm_default_local_model=s.get("llm_default_local_model"),
        llm_default_temperature=s.get("llm_default_temperature"),
    )


@router.put("/llm", response_model=LlmSettingsPayload)
async def update_llm_settings(
    body: LlmSettingsPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LlmSettingsPayload:
    current = dict(user.settings or {})
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            current.pop(field, None)
        elif field == "llm_providers" and isinstance(value, dict):
            serialized = {}
            for k, v in value.items():
                if isinstance(v, dict):
                    serialized[k] = v
                else:
                    serialized[k] = v.model_dump() if hasattr(v, "model_dump") else v
            current[field] = serialized
        else:
            current[field] = value
    user.settings = current
    flag_modified(user, "settings")
    await db.flush()

    raw_providers = current.get("llm_providers")
    providers = None
    if raw_providers and isinstance(raw_providers, dict):
        providers = {
            k: LlmProviderConfig(**v) if isinstance(v, dict) else v
            for k, v in raw_providers.items()
        }
    return LlmSettingsPayload(
        llm_providers=providers,
        llm_default_model=current.get("llm_default_model"),
        llm_default_local_model=current.get("llm_default_local_model"),
        llm_default_temperature=current.get("llm_default_temperature"),
    )


# --- Extension API-Key ---

API_KEY_PREFIX = "tpk_"


class ApiKeyResponse(BaseModel):
    api_key: str
    created_at: str


class ApiKeyStatus(BaseModel):
    has_key: bool
    created_at: str | None = None


@router.get("/extension-api-key", response_model=ApiKeyStatus)
async def get_api_key_status(
    user: User = Depends(get_current_user),
) -> ApiKeyStatus:
    """Pruefen ob ein Extension-API-Key existiert."""
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")
    s = user.settings or {}
    has_key = bool(s.get("extension_api_key_hash"))
    return ApiKeyStatus(
        has_key=has_key,
        created_at=s.get("extension_api_key_created_at"),
    )


@router.post("/extension-api-key", response_model=ApiKeyResponse)
async def generate_api_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    """Neuen Extension-API-Key generieren (invalidiert vorherigen)."""
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")

    raw_key = secrets.token_hex(32)
    api_key = f"{API_KEY_PREFIX}{raw_key}"

    key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()
    now = datetime.now(timezone.utc).isoformat()

    current = dict(user.settings or {})
    current["extension_api_key_hash"] = key_hash
    current["extension_api_key_created_at"] = now
    user.settings = current
    flag_modified(user, "settings")
    await db.flush()

    return ApiKeyResponse(api_key=api_key, created_at=now)


@router.delete("/extension-api-key")
async def revoke_api_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Extension-API-Key widerrufen."""
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner")

    current = dict(user.settings or {})
    current.pop("extension_api_key_hash", None)
    current.pop("extension_api_key_created_at", None)
    user.settings = current
    flag_modified(user, "settings")
    await db.flush()

    return {"ok": True, "message": "API-Key widerrufen"}
