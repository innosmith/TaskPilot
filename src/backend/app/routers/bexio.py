"""FastAPI Router für Bexio Buchhaltung (Frontend-Zugriff)."""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bexio"))
from bexio_client import BexioClient, BexioConfig  # noqa: E402

router = APIRouter(prefix="/api/bexio", tags=["bexio"])


def _get_bexio_client(user: User) -> BexioClient:
    """Bexio-Client aus User-Settings oder Env-Variablen erstellen."""
    settings = user.settings or {}
    token = settings.get("bexio_api_token") or ""

    if not token:
        from app.config import get_settings
        app_cfg = get_settings()
        token = app_cfg.bexio_api_token

    if not token:
        raise HTTPException(status_code=400, detail="Bexio API-Token nicht konfiguriert")

    return BexioClient(BexioConfig(api_token=token))


@router.get("/test-connection")
async def test_connection(user: User = Depends(get_current_user)):
    import logging
    logger = logging.getLogger("taskpilot.bexio")
    try:
        client = _get_bexio_client(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bexio Client-Erstellung fehlgeschlagen: %s", e)
        raise HTTPException(status_code=400, detail=f"Client-Fehler: {e}")
    try:
        result = await client.test_connection()
        return result
    except Exception as e:
        logger.error("Bexio Verbindungstest fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}")


class ContactSummary(BaseModel):
    id: int
    name_1: str
    name_2: str | None = None
    mail: str | None = None
    contact_type_id: int | None = None


@router.get("/contacts", response_model=list[ContactSummary])
async def list_contacts(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
):
    client = _get_bexio_client(user)
    contacts = await client.list_contacts(limit=limit)
    return [
        ContactSummary(
            id=c.get("id", 0), name_1=c.get("name_1", ""),
            name_2=c.get("name_2"), mail=c.get("mail"),
            contact_type_id=c.get("contact_type_id"),
        )
        for c in contacts
    ]


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: int, user: User = Depends(get_current_user)):
    client = _get_bexio_client(user)
    return await client.get_contact(contact_id)


@router.get("/contacts/{contact_id}/orders")
async def list_orders_for_contact(
    contact_id: int,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
):
    client = _get_bexio_client(user)
    return await client.list_orders(contact_id=contact_id, limit=limit)


class ProjectSummary(BaseModel):
    id: int
    name: str
    contact_id: int | None = None
    status_id: int | None = None


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
):
    client = _get_bexio_client(user)
    projects = await client.list_projects(limit=limit)
    return [
        ProjectSummary(
            id=p.get("id", 0), name=p.get("name", ""),
            contact_id=p.get("contact_id"),
            status_id=p.get("pr_state_id"),
        )
        for p in projects
    ]


@router.get("/search")
async def search_bexio(
    q: str = Query(min_length=1),
    user: User = Depends(get_current_user),
):
    client = _get_bexio_client(user)
    contacts = await client.search_contact_by_name(q)
    return {
        "contacts": [
            {"id": c.get("id"), "name_1": c.get("name_1"), "name_2": c.get("name_2"), "mail": c.get("mail")}
            for c in contacts
        ],
    }
