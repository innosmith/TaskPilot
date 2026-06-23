"""Router für OneDrive-Datei-Browsing (Chat-Kontext-Quellen)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import require_role
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
    from app.services.graph import get_graph_client

    return get_graph_client()


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
    _user: User = Depends(require_role("owner")),
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
        logger.exception("OneDrive list_files fehlgeschlagen")
        raise HTTPException(status_code=500, detail="OneDrive-Dateien konnten nicht geladen werden")


@router.get("/search", response_model=DriveSearchResponse)
async def search_files(
    q: str = Query(..., min_length=1, description="Suchbegriff"),
    top: int = Query(20, ge=1, le=50),
    _user: User = Depends(require_role("owner")),
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
        logger.exception("OneDrive search fehlgeschlagen")
        raise HTTPException(status_code=500, detail="OneDrive-Suche fehlgeschlagen")


@router.get("/metadata")
async def get_metadata(
    item_id: str = Query(..., description="OneDrive Item-ID"),
    _user: User = Depends(require_role("owner")),
):
    """Metadaten einer OneDrive-Datei lesen."""
    client = _get_graph_client()
    if not client:
        raise HTTPException(status_code=503, detail="Graph API nicht konfiguriert")

    try:
        item = await client.get_drive_item(item_id)
        return _item_to_drive_item(item)
    except Exception as e:
        logger.exception("OneDrive metadata fehlgeschlagen")
        raise HTTPException(status_code=500, detail="OneDrive-Metadaten konnten nicht geladen werden")
