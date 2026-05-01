"""FastAPI Router für Toggl Track Zeiterfassung (Frontend-Zugriff)."""

import logging
import sys
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "toggl"))
from toggl_client import TogglClient, TogglConfig  # noqa: E402

logger = logging.getLogger("taskpilot.toggl.router")

router = APIRouter(prefix="/api/toggl", tags=["toggl"])

# ── Cache-Layer (analog Pipedrive) ───────────────────────
_project_cache: TTLCache = TTLCache(maxsize=200, ttl=1800)
_summary_cache: TTLCache = TTLCache(maxsize=50, ttl=900)
_entry_cache: TTLCache = TTLCache(maxsize=100, ttl=600)
_static_cache: TTLCache = TTLCache(maxsize=50, ttl=3600)


def _get_toggl_client(user: User) -> TogglClient:
    """Toggl-Client aus User-Settings oder Env-Variablen erstellen."""
    settings = user.settings or {}
    token = settings.get("toggl_api_token") or ""
    ws_id = settings.get("toggl_workspace_id") or 0

    if not token:
        from app.config import get_settings
        app_cfg = get_settings()
        token = app_cfg.toggl_api_token
        ws_id = ws_id or app_cfg.toggl_workspace_id

    if not token:
        raise HTTPException(status_code=400, detail="Toggl API-Token nicht konfiguriert")

    return TogglClient(TogglConfig(api_token=token, workspace_id=int(ws_id or 0)))


# ── Verbindungstest ──────────────────────────────────────

@router.get("/test-connection")
async def test_connection(user: User = Depends(get_current_user)):
    try:
        client = _get_toggl_client(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Toggl Client-Erstellung fehlgeschlagen: %s", e)
        raise HTTPException(status_code=400, detail=f"Client-Fehler: {e}")
    try:
        result = await client.test_connection()
        return result
    except Exception as e:
        logger.error("Toggl Verbindungstest fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}")


# ── Workspaces ───────────────────────────────────────────

class WorkspaceSummary(BaseModel):
    id: int
    name: str


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_workspaces(user: User = Depends(get_current_user)):
    cached = _static_cache.get("workspaces")
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    ws = await client.list_workspaces()
    result = [WorkspaceSummary(id=w.get("id", 0), name=w.get("name", "")) for w in ws]
    _static_cache["workspaces"] = result
    return result


# ── Clients ──────────────────────────────────────────────

class ClientSummary(BaseModel):
    id: int
    name: str
    archived: bool = False


@router.get("/clients", response_model=list[ClientSummary])
async def list_clients(user: User = Depends(get_current_user)):
    cached = _static_cache.get("clients")
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    clients = await client.list_clients()
    result = [ClientSummary(id=c.get("id", 0), name=c.get("name", ""), archived=c.get("archived", False)) for c in clients]
    _static_cache["clients"] = result
    return result


# ── Projects ─────────────────────────────────────────────

class ProjectSummary(BaseModel):
    id: int
    name: str
    client_id: int | None = None
    active: bool = True
    billable: bool | None = None
    rate: int | None = None
    currency: str | None = None


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(
    active: bool = True,
    user: User = Depends(get_current_user),
):
    cache_key = f"projects:{active}"
    cached = _project_cache.get(cache_key)
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    projects = await client.list_projects(active=active)
    result = [
        ProjectSummary(
            id=p.get("id", 0), name=p.get("name", ""),
            client_id=p.get("client_id"), active=p.get("active", True),
            billable=p.get("billable"),
            rate=p.get("rate"),
            currency=p.get("currency"),
        )
        for p in projects
    ]
    _project_cache[cache_key] = result
    return result


@router.get("/projects/{project_id}")
async def get_project_with_rate(
    project_id: int,
    user: User = Depends(get_current_user),
):
    cache_key = f"project:{project_id}"
    cached = _project_cache.get(cache_key)
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    result = await client.get_project_with_rate(project_id)
    _project_cache[cache_key] = result
    return result


# ── Summary Reports ──────────────────────────────────────

@router.get("/projects-summary")
async def get_projects_summary(
    start_date: str = Query(...),
    end_date: str = Query(...),
    user: User = Depends(get_current_user),
):
    cache_key = f"proj_summary:{start_date}:{end_date}"
    cached = _summary_cache.get(cache_key)
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    result = await client.get_projects_summary(start_date, end_date)
    _summary_cache[cache_key] = result
    return result


@router.get("/summary-by-project")
async def get_summary_by_project(
    start_date: str = Query(...),
    end_date: str = Query(...),
    billable: bool = Query(default=True),
    user: User = Depends(get_current_user),
):
    cache_key = f"summary_proj:{start_date}:{end_date}:{billable}"
    cached = _summary_cache.get(cache_key)
    if cached is not None:
        return cached
    client = _get_toggl_client(user)
    result = await client.get_summary_by_project(start_date, end_date, billable=billable)
    _summary_cache[cache_key] = result
    return result


# ── Suche ────────────────────────────────────────────────

@router.get("/search")
async def search_toggl(
    q: str = Query(min_length=1),
    user: User = Depends(get_current_user),
):
    client = _get_toggl_client(user)
    clients = await client.search_clients(q)
    projects = await client.search_projects(q)
    return {
        "clients": [{"id": c.get("id"), "name": c.get("name")} for c in clients],
        "projects": [{"id": p.get("id"), "name": p.get("name"), "client_id": p.get("client_id")} for p in projects],
    }


# ── Cache-Verwaltung ─────────────────────────────────────

@router.post("/cache/clear")
async def clear_cache(user: User = Depends(get_current_user)):
    _project_cache.clear()
    _summary_cache.clear()
    _entry_cache.clear()
    _static_cache.clear()
    logger.info("Toggl-Caches manuell geleert")
    return {"status": "ok", "message": "Alle Toggl-Caches geleert"}


@router.get("/cache/stats")
async def cache_stats(user: User = Depends(get_current_user)):
    return {
        "project_cache": {"size": len(_project_cache), "maxsize": _project_cache.maxsize, "ttl": _project_cache.ttl},
        "summary_cache": {"size": len(_summary_cache), "maxsize": _summary_cache.maxsize, "ttl": _summary_cache.ttl},
        "entry_cache": {"size": len(_entry_cache), "maxsize": _entry_cache.maxsize, "ttl": _entry_cache.ttl},
        "static_cache": {"size": len(_static_cache), "maxsize": _static_cache.maxsize, "ttl": _static_cache.ttl},
    }
