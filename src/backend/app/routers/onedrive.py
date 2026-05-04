"""Router für OneDrive-Datei-Browsing (Chat-Kontext-Quellen)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onedrive", tags=["onedrive"])


class DriveItem(BaseModel):
    id: str
    name: str
    size: int = 0
    is_folder: bool = False
    web_url: str = ""
    last_modified: str = ""
    mime_type: str = ""
    path: str = ""


class DriveListResponse(BaseModel):
    items: list[DriveItem]
    path: str


class DriveSearchResponse(BaseModel):
    items: list[DriveItem]
    query: str


def _get_graph_client():
    """Erstellt einen GraphClient mit den konfigurierten Credentials."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
    from graph_client import GraphClient, GraphConfig

    s = get_settings()
    if not s.graph_tenant_id or not s.graph_client_id:
        return None

    config = GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    )
    return GraphClient(config)


def _item_to_drive_item(item: dict) -> DriveItem:
    """Konvertiert ein Graph-API-Item in ein DriveItem."""
    return DriveItem(
        id=item.get("id", ""),
        name=item.get("name", ""),
        size=item.get("size", 0),
        is_folder=bool(item.get("folder")),
        web_url=item.get("webUrl", ""),
        last_modified=item.get("lastModifiedDateTime", ""),
        mime_type=(item.get("file") or {}).get("mimeType", ""),
        path=(item.get("parentReference") or {}).get("path", ""),
    )


@router.get("/list", response_model=DriveListResponse)
async def list_files(
    path: str = Query("/", description="OneDrive-Ordnerpfad"),
    top: int = Query(50, ge=1, le=200),
    _user: User = Depends(get_current_user),
):
    """Listet Dateien und Ordner in einem OneDrive-Verzeichnis auf."""
    client = _get_graph_client()
    if not client:
        raise HTTPException(status_code=503, detail="Graph API nicht konfiguriert")

    try:
        items = await client.list_drive_items(path=path, top=top)
        drive_items = [_item_to_drive_item(item) for item in items]
        drive_items.sort(key=lambda x: (not x.is_folder, x.name.lower()))
        return DriveListResponse(items=drive_items, path=path)
    except Exception as e:
        logger.error("OneDrive list_files fehlgeschlagen: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=DriveSearchResponse)
async def search_files(
    q: str = Query(..., min_length=1, description="Suchbegriff"),
    top: int = Query(20, ge=1, le=50),
    _user: User = Depends(get_current_user),
):
    """Volltextsuche über OneDrive-Dateien."""
    client = _get_graph_client()
    if not client:
        raise HTTPException(status_code=503, detail="Graph API nicht konfiguriert")

    try:
        items = await client.search_drive(query=q, top=top)
        drive_items = [_item_to_drive_item(item) for item in items]
        return DriveSearchResponse(items=drive_items, query=q)
    except Exception as e:
        logger.error("OneDrive search fehlgeschlagen: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata")
async def get_metadata(
    item_id: str = Query(..., description="OneDrive Item-ID"),
    _user: User = Depends(get_current_user),
):
    """Metadaten einer OneDrive-Datei lesen."""
    client = _get_graph_client()
    if not client:
        raise HTTPException(status_code=503, detail="Graph API nicht konfiguriert")

    try:
        item = await client.get_drive_item(item_id)
        return _item_to_drive_item(item)
    except Exception as e:
        logger.error("OneDrive metadata fehlgeschlagen: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
