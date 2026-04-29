"""FastAPI Router für Toggl Track Zeiterfassung (Frontend-Zugriff)."""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "toggl"))
from toggl_client import TogglClient, TogglConfig  # noqa: E402

router = APIRouter(prefix="/api/toggl", tags=["toggl"])


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


@router.get("/test-connection")
async def test_connection(user: User = Depends(get_current_user)):
    import logging
    logger = logging.getLogger("taskpilot.toggl")
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


class WorkspaceSummary(BaseModel):
    id: int
    name: str


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_workspaces(user: User = Depends(get_current_user)):
    client = _get_toggl_client(user)
    ws = await client.list_workspaces()
    return [WorkspaceSummary(id=w.get("id", 0), name=w.get("name", "")) for w in ws]


class ClientSummary(BaseModel):
    id: int
    name: str
    archived: bool = False


@router.get("/clients", response_model=list[ClientSummary])
async def list_clients(user: User = Depends(get_current_user)):
    client = _get_toggl_client(user)
    clients = await client.list_clients()
    return [ClientSummary(id=c.get("id", 0), name=c.get("name", ""), archived=c.get("archived", False)) for c in clients]


class ProjectSummary(BaseModel):
    id: int
    name: str
    client_id: int | None = None
    active: bool = True
    billable: bool | None = None


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(
    active: bool = True,
    user: User = Depends(get_current_user),
):
    client = _get_toggl_client(user)
    projects = await client.list_projects(active=active)
    return [
        ProjectSummary(
            id=p.get("id", 0), name=p.get("name", ""),
            client_id=p.get("client_id"), active=p.get("active", True),
            billable=p.get("billable"),
        )
        for p in projects
    ]


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
