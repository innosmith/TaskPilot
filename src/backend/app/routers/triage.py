"""FastAPI-Router für E-Mail-Triage: Triage-Vorschläge anzeigen, Aktionen ausführen."""

import uuid
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import AgentJob, EmailTriage, User
from app.schemas import EmailTriageOut, EmailTriageUpdate
from app.services.triage import run_triage_now

logger = logging.getLogger("taskpilot.triage.router")
router = APIRouter(prefix="/api/triage", tags=["triage"])


def _require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner dürfen Triage-Daten sehen")


@router.get("", response_model=list[EmailTriageOut])
async def list_triage_items(
    status_filter: str | None = Query(None, alias="status"),
    triage_class: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EmailTriageOut]:
    _require_owner(user)
    query = select(EmailTriage).order_by(EmailTriage.created_at.desc())
    if status_filter:
        query = query.where(EmailTriage.status == status_filter)
    if triage_class:
        query = query.where(EmailTriage.triage_class == triage_class)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/stats")
async def triage_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_owner(user)
    result = await db.execute(
        select(EmailTriage.status, func.count(EmailTriage.id))
        .group_by(EmailTriage.status)
    )
    by_status = {row[0]: row[1] for row in result.all()}

    result2 = await db.execute(
        select(EmailTriage.triage_class, func.count(EmailTriage.id))
        .where(EmailTriage.status == "pending")
        .group_by(EmailTriage.triage_class)
    )
    by_class = {row[0] or "unclassified": row[1] for row in result2.all()}

    return {
        "by_status": by_status,
        "by_class": by_class,
        "total_pending": by_status.get("pending", 0),
    }


@router.post("/run", status_code=200)
async def trigger_triage(
    top: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> dict:
    """Manuell Triage für die letzten E-Mails auslösen."""
    _require_owner(user)
    count = await run_triage_now(top=top)
    return {"status": "completed", "classified": count}


@router.get("/{triage_id}", response_model=EmailTriageOut)
async def get_triage_item(
    triage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmailTriageOut:
    _require_owner(user)
    result = await db.execute(select(EmailTriage).where(EmailTriage.id == triage_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Triage-Eintrag nicht gefunden")
    return item


@router.patch("/{triage_id}", response_model=EmailTriageOut)
async def update_triage_item(
    triage_id: uuid.UUID,
    body: EmailTriageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmailTriageOut:
    _require_owner(user)
    result = await db.execute(select(EmailTriage).where(EmailTriage.id == triage_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Triage-Eintrag nicht gefunden")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    return item


@router.post("/{triage_id}/dismiss", status_code=200)
async def dismiss_triage_item(
    triage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_owner(user)
    result = await db.execute(select(EmailTriage).where(EmailTriage.id == triage_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Triage-Eintrag nicht gefunden")
    item.status = "dismissed"
    return {"status": "dismissed", "id": str(triage_id)}


@router.post("/{triage_id}/act", status_code=200)
async def act_on_triage_item(
    triage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Triage-Vorschlag annehmen und Aktion ausführen."""
    _require_owner(user)
    result = await db.execute(select(EmailTriage).where(EmailTriage.id == triage_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Triage-Eintrag nicht gefunden")

    item.status = "acted"
    action = item.suggested_action or {}
    action_type = action.get("type", "human_review")

    return {
        "status": "acted",
        "id": str(triage_id),
        "action_type": action_type,
        "triage_class": item.triage_class,
        "message_id": item.message_id,
    }


@router.get("/activity/feed")
async def triage_activity_feed(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Activity-Feed: Was hat der Agent getan? Letzte Triage-Aktionen + AgentJob-Ergebnisse."""
    _require_owner(user)

    since = datetime.now(timezone.utc) - timedelta(days=7)

    jobs_q = (
        select(AgentJob)
        .where(
            AgentJob.job_type.in_(["email_triage", "draft_email_reply", "create_task_from_email"]),
            AgentJob.created_at >= since,
        )
        .order_by(AgentJob.created_at.desc())
        .limit(limit)
    )
    jobs_result = await db.execute(jobs_q)
    jobs = list(jobs_result.scalars().all())

    activities = []
    for job in jobs:
        meta = job.metadata_json or {}
        activities.append({
            "id": str(job.id),
            "job_type": job.job_type,
            "status": job.status,
            "subject": meta.get("subject", ""),
            "from_address": meta.get("from_address", ""),
            "output": job.output,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        })

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stats_q = await db.execute(
        select(
            func.count(AgentJob.id).filter(
                and_(AgentJob.status == "awaiting_approval", AgentJob.created_at >= today)
            ).label("drafts_pending"),
            func.count(AgentJob.id).filter(
                and_(AgentJob.status == "completed", AgentJob.job_type == "email_triage", AgentJob.created_at >= today)
            ).label("classified_today"),
        )
    )
    stats_row = stats_q.one()

    return {
        "activities": activities,
        "summary": {
            "drafts_pending": stats_row.drafts_pending,
            "classified_today": stats_row.classified_today,
        },
    }
