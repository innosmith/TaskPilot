"""E-Mail-Endpoints -- Graph API für Cockpit-Frontend exponieren.

Nur owner darf auf E-Mails zugreifen (Guard via get_current_user + role check).
"""

import sys
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import AgentJob, User

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("taskpilot.emails")
router = APIRouter(prefix="/api/emails", tags=["emails"])

_graph_client: GraphClient | None = None


def _get_graph_client() -> GraphClient:
    global _graph_client
    if _graph_client is None:
        settings = get_settings()
        config = GraphConfig(
            tenant_id=settings.graph_tenant_id,
            client_id=settings.graph_client_id,
            client_secret=settings.graph_client_secret,
            user_email=settings.graph_user_email,
        )
        _graph_client = GraphClient(config)
    return _graph_client


def _require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="E-Mail-Zugriff nur für Owner",
        )


def _check_configured() -> None:
    settings = get_settings()
    if not settings.graph_tenant_id or not settings.graph_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph API nicht konfiguriert. Setze TP_GRAPH_TENANT_ID, TP_GRAPH_CLIENT_ID, TP_GRAPH_CLIENT_SECRET, TP_GRAPH_USER_EMAIL in der Umgebung.",
        )


# ── Schemas ──────────────────────────────────────────────────

class EmailSummary(BaseModel):
    id: str
    subject: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    received_at: str | None = None
    is_read: bool = False
    body_preview: str | None = None
    categories: list[str] = []
    inference_classification: str | None = None
    importance: str | None = None
    has_attachments: bool = False


class EmailListResponse(BaseModel):
    emails: list[EmailSummary]
    total: int | None = None


class EmailDetail(BaseModel):
    id: str
    subject: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    to_recipients: list[str] = []
    cc_recipients: list[str] = []
    received_at: str | None = None
    body_html: str | None = None
    body_preview: str | None = None
    categories: list[str] = []
    inference_classification: str | None = None
    importance: str | None = None
    has_attachments: bool = False
    is_read: bool = False


class FolderInfo(BaseModel):
    id: str
    display_name: str
    total_count: int = 0


class DraftCreateRequest(BaseModel):
    subject: str
    body_html: str
    to_recipients: list[str]
    cc_recipients: list[str] | None = None
    reply_to_id: str | None = None


class DraftResponse(BaseModel):
    id: str
    subject: str | None = None
    status: str = "draft_created"


# ── Endpoints ────────────────────────────────────────────────

@router.get("/folders", response_model=list[FolderInfo])
async def list_folders(
    user: User = Depends(get_current_user),
) -> list[FolderInfo]:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        folders = await client.list_folders()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return [
        FolderInfo(
            id=f.get("id", ""),
            display_name=f.get("displayName", ""),
            total_count=f.get("totalItemCount", 0),
        )
        for f in folders
    ]


@router.get("", response_model=EmailListResponse)
async def list_emails(
    folder: str = Query("inbox"),
    top: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    user: User = Depends(get_current_user),
) -> EmailListResponse:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    filter_str = "isRead eq false" if unread_only else None
    try:
        data = await client.list_emails(folder=folder, top=top, skip=skip, filter_str=filter_str)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    emails = []
    for msg in data.get("value", []):
        from_obj = msg.get("from", {}).get("emailAddress", {})
        emails.append(EmailSummary(
            id=msg.get("id", ""),
            subject=msg.get("subject"),
            from_address=from_obj.get("address"),
            from_name=from_obj.get("name"),
            received_at=msg.get("receivedDateTime"),
            is_read=msg.get("isRead", False),
            body_preview=msg.get("bodyPreview", "")[:250],
            categories=msg.get("categories", []),
            inference_classification=msg.get("inferenceClassification"),
            importance=msg.get("importance"),
            has_attachments=msg.get("hasAttachments", False),
        ))
    return EmailListResponse(emails=emails, total=len(emails))


@router.get("/{message_id}", response_model=EmailDetail)
async def get_email(
    message_id: str,
    user: User = Depends(get_current_user),
) -> EmailDetail:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        msg = await client.get_email(message_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    from_obj = msg.get("from", {}).get("emailAddress", {})
    body = msg.get("body", {})
    return EmailDetail(
        id=msg.get("id", ""),
        subject=msg.get("subject"),
        from_address=from_obj.get("address"),
        from_name=from_obj.get("name"),
        to_recipients=[
            r.get("emailAddress", {}).get("address", "")
            for r in msg.get("toRecipients", [])
        ],
        cc_recipients=[
            r.get("emailAddress", {}).get("address", "")
            for r in msg.get("ccRecipients", [])
        ],
        received_at=msg.get("receivedDateTime"),
        body_html=body.get("content") if body.get("contentType") == "html" else None,
        body_preview=msg.get("bodyPreview"),
        categories=msg.get("categories", []),
        inference_classification=msg.get("inferenceClassification"),
        importance=msg.get("importance"),
        has_attachments=msg.get("hasAttachments", False),
        is_read=msg.get("isRead", False),
    )


@router.post("/drafts", response_model=DraftResponse, status_code=201)
async def create_draft(
    body: DraftCreateRequest,
    user: User = Depends(get_current_user),
) -> DraftResponse:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    draft = await client.create_draft(
        subject=body.subject,
        body_html=body.body_html,
        to_recipients=body.to_recipients,
        cc_recipients=body.cc_recipients,
        reply_to_id=body.reply_to_id,
    )
    return DraftResponse(
        id=draft.get("id", ""),
        subject=draft.get("subject"),
    )


@router.post("/{message_id}/send", status_code=200)
async def send_draft(
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Erstellt einen Approval-Job statt direkt zu senden (HITL-Enforcement)."""
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        msg = await client.get_email(message_id)
    except Exception:
        msg = {}

    subject = msg.get("subject", "(kein Betreff)")
    to_addrs = [
        r.get("emailAddress", {}).get("address", "")
        for r in msg.get("toRecipients", [])
    ]

    job = AgentJob(
        task_id=None,
        job_type="send_email",
        status="awaiting_approval",
        metadata_json={
            "draft_id": message_id,
            "subject": subject,
            "to_recipients": to_addrs,
        },
    )
    db.add(job)
    await db.flush()
    return {
        "status": "awaiting_approval",
        "job_id": str(job.id),
        "message": "Entwurf wartet auf Freigabe in der Agent-Queue",
    }


@router.patch("/{message_id}/read", status_code=200)
async def mark_as_read(
    message_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    await client.mark_as_read(message_id)
    return {"status": "marked_as_read", "message_id": message_id}
