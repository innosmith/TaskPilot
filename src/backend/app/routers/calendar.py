"""FastAPI-Router für Kalender-Zugriff via Microsoft Graph API."""

import logging
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("taskpilot.calendar")
router = APIRouter(prefix="/api/calendar", tags=["calendar"])

_graph_client: GraphClient | None = None


def _get_graph_client() -> GraphClient:
    global _graph_client
    if _graph_client is None:
        s = get_settings()
        config = GraphConfig(
            tenant_id=s.graph_tenant_id,
            client_id=s.graph_client_id,
            client_secret=s.graph_client_secret,
            user_email=s.graph_user_email,
        )
        _graph_client = GraphClient(config)
    return _graph_client


def _require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner dürfen auf den Kalender zugreifen")


def _check_configured() -> None:
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        raise HTTPException(
            status_code=503,
            detail="Graph API nicht konfiguriert. Setze TP_GRAPH_* in der Umgebung.",
        )


# ── Schemas ──────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    id: str
    subject: str | None
    start: str | None
    end: str | None
    is_all_day: bool = False
    location: str | None = None
    show_as: str | None = None
    body_preview: str | None = None
    organizer: str | None = None
    categories: list[str] = []
    sensitivity: str | None = None
    attendees_count: int = 0
    is_organizer: bool = False


class EventCreateRequest(BaseModel):
    subject: str
    start: str
    end: str
    body: str | None = None
    location: str | None = None
    show_as: str = "busy"


class FreeSlot(BaseModel):
    start: str
    end: str
    duration_minutes: int


# ── Endpoints ────────────────────────────────────────────────

@router.get("/events", response_model=list[CalendarEvent])
async def list_events(
    start: str = Query(..., description="Start ISO 8601"),
    end: str = Query(..., description="End ISO 8601"),
    top: int = Query(50, ge=1, le=100),
    exclude_categories: str | None = Query(None, description="Kommagetrennte Kategorien zum Ausblenden"),
    hide_private: bool = Query(True, description="Termine mit sensitivity=private ausblenden"),
    hide_free: bool = Query(True, description="Termine mit showAs=free ausblenden"),
    user: User = Depends(get_current_user),
) -> list[CalendarEvent]:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        events = await client.list_events(start, end, top)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    excluded = set()
    if exclude_categories:
        excluded = {c.strip().lower() for c in exclude_categories.split(",") if c.strip()}

    result = []
    for ev in events:
        if ev.get("isCancelled", False):
            continue
        if hide_free and ev.get("showAs") == "free":
            continue
        if hide_private and ev.get("sensitivity") == "private":
            continue

        cats = ev.get("categories", []) or []
        cats_lower = {c.lower() for c in cats}
        if excluded and cats_lower & excluded:
            continue

        org = ev.get("organizer", {}).get("emailAddress", {})
        attendees = ev.get("attendees", []) or []
        result.append(CalendarEvent(
            id=ev.get("id", ""),
            subject=ev.get("subject"),
            start=ev.get("start", {}).get("dateTime"),
            end=ev.get("end", {}).get("dateTime"),
            is_all_day=ev.get("isAllDay", False),
            location=(ev.get("location") or {}).get("displayName"),
            show_as=ev.get("showAs"),
            body_preview=ev.get("bodyPreview", "")[:200],
            organizer=org.get("name") or org.get("address"),
            categories=cats,
            sensitivity=ev.get("sensitivity"),
            attendees_count=len(attendees),
            is_organizer=ev.get("isOrganizer", False),
        ))
    return result


@router.post("/events", response_model=CalendarEvent, status_code=201)
async def create_event(
    body: EventCreateRequest,
    user: User = Depends(get_current_user),
) -> CalendarEvent:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        ev = await client.create_event(
            subject=body.subject,
            start=body.start,
            end=body.end,
            body=body.body,
            location=body.location,
            show_as=body.show_as,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return CalendarEvent(
        id=ev.get("id", ""),
        subject=ev.get("subject"),
        start=ev.get("start", {}).get("dateTime"),
        end=ev.get("end", {}).get("dateTime"),
        is_all_day=ev.get("isAllDay", False),
        show_as=ev.get("showAs"),
    )


@router.get("/free-slots", response_model=list[FreeSlot])
async def find_free_slots(
    start: str = Query(...),
    end: str = Query(...),
    duration: int = Query(60, ge=15, le=480, description="Gewünschte Dauer in Minuten"),
    user: User = Depends(get_current_user),
) -> list[FreeSlot]:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        slots = await client.find_free_slots(start, end, duration)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return [FreeSlot(**s) for s in slots]


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
) -> None:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        await client.delete_event(event_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
