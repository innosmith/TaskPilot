import uuid
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import AgentJob, Task, User
from app.schemas import AgentJobCreate, AgentJobOut, AgentJobUpdate, AgentJobWithTask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402
from app.config import get_settings  # noqa: E402

router = APIRouter(prefix="/api/agent-jobs", tags=["agent-jobs"])


def _get_email_client() -> GraphClient | None:
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return None
    config = GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    )
    return GraphClient(config)


def _extract_draft_id(job: AgentJob) -> str | None:
    """Extrahiert die draft_id aus Metadata oder LLM-Output."""
    meta = job.metadata_json or {}
    draft_id = meta.get("draft_id")
    if draft_id:
        return draft_id

    if not job.output:
        return None

    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", job.output, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            draft_id = parsed.get("draft_id")
            if draft_id:
                return draft_id
        except json.JSONDecodeError:
            pass

    id_match = re.search(r"AAMk[A-Za-z0-9_-]{20,}", job.output)
    if id_match:
        return id_match.group(0)

    return None


@router.get("", response_model=list[AgentJobWithTask])
async def list_agent_jobs(
    status: str | None = None,
    task_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AgentJobWithTask]:
    query = select(AgentJob, Task.title).outerjoin(Task, AgentJob.task_id == Task.id)
    if status:
        query = query.where(AgentJob.status == status)
    if task_id:
        query = query.where(AgentJob.task_id == task_id)
    query = query.order_by(AgentJob.created_at.desc())

    result = await db.execute(query)
    rows = result.all()
    return [
        AgentJobWithTask.model_validate({**job.__dict__, "task_title": title})
        for job, title in rows
    ]


@router.get("/{job_id}", response_model=AgentJobWithTask)
async def get_agent_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AgentJobWithTask:
    result = await db.execute(
        select(AgentJob, Task.title)
        .outerjoin(Task, AgentJob.task_id == Task.id)
        .where(AgentJob.id == job_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    job, title = row
    return AgentJobWithTask.model_validate({**job.__dict__, "task_title": title})


@router.get("/{job_id}/draft-preview")
async def get_draft_preview(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Lädt den Draft-Inhalt aus Outlook für die Vorschau im Approval-Flow."""
    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")

    draft_id = _extract_draft_id(job)
    if not draft_id:
        raise HTTPException(status_code=404, detail="Kein Entwurf mit diesem Job verknüpft")

    client = _get_email_client()
    if not client:
        raise HTTPException(status_code=503, detail="Graph API nicht konfiguriert")

    meta = job.metadata_json or {}
    try:
        draft = await client.get_email(draft_id)
        to_list = [
            r.get("emailAddress", {}).get("address", "")
            for r in draft.get("toRecipients", [])
        ]
        cc_list = [
            r.get("emailAddress", {}).get("address", "")
            for r in draft.get("ccRecipients", [])
        ]
        return {
            "draft_id": draft_id,
            "subject": draft.get("subject"),
            "body_html": draft.get("body", {}).get("content"),
            "body_preview": draft.get("bodyPreview"),
            "to_recipients": to_list,
            "cc_recipients": cc_list,
            "source_subject": meta.get("subject"),
            "source_from": meta.get("from_address"),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Draft konnte nicht geladen werden: {e}")
    finally:
        await client.close()


@router.post("", response_model=AgentJobOut, status_code=201)
async def create_agent_job(
    body: AgentJobCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AgentJobOut:
    task_result = await db.execute(select(Task).where(Task.id == body.task_id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    job = AgentJob(task_id=body.task_id, llm_model=body.llm_model)
    db.add(job)
    await db.flush()
    return job


@router.patch("/{job_id}", response_model=AgentJobOut)
async def update_agent_job(
    job_id: uuid.UUID,
    body: AgentJobUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AgentJobOut:
    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")

    old_status = job.status

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(job, field, value)

    if body.status == "running" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if body.status in ("completed", "failed") and job.completed_at is None:
        job.completed_at = datetime.now(timezone.utc)

    if (
        old_status == "awaiting_approval"
        and body.status == "completed"
        and job.job_type in ("send_email", "email_triage")
    ):
        draft_id = _extract_draft_id(job)
        if draft_id:
            client = _get_email_client()
            if client:
                try:
                    await client.send_draft(draft_id)
                    job.output = (job.output or "") + "\n\nE-Mail erfolgreich gesendet."
                except Exception as e:
                    job.status = "failed"
                    job.error_message = str(e)
                finally:
                    await client.close()

    if (
        old_status == "awaiting_approval"
        and body.status == "failed"
        and job.job_type in ("send_email", "email_triage")
    ):
        draft_id = _extract_draft_id(job)
        if draft_id:
            client = _get_email_client()
            if client:
                try:
                    await client.delete_message(draft_id)
                    job.output = (job.output or "") + "\n\nEntwurf gelöscht."
                except Exception:
                    pass
                finally:
                    await client.close()

    return job


_DELETABLE_STATUSES = {"completed", "failed"}


class BulkDeleteResult(BaseModel):
    deleted: int


@router.delete("/bulk", response_model=BulkDeleteResult)
async def bulk_delete_agent_jobs(
    status: str = Query(..., description="Status der zu löschenden Jobs"),
    older_than_days: int | None = Query(None, ge=0, description="Nur Jobs älter als X Tage löschen"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BulkDeleteResult:
    """Bulk-Löschung von abgeschlossenen/fehlgeschlagenen Jobs."""
    if status == "both":
        status_filter = AgentJob.status.in_(list(_DELETABLE_STATUSES))
    elif status in _DELETABLE_STATUSES:
        status_filter = AgentJob.status == status
    else:
        raise HTTPException(status_code=400, detail="status muss 'completed', 'failed' oder 'both' sein")

    conditions = [status_filter]
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        conditions.append(AgentJob.created_at < cutoff)

    count_result = await db.execute(
        select(func.count()).where(and_(*conditions)).select_from(AgentJob)
    )
    count = count_result.scalar_one()

    if count > 0:
        await db.execute(delete(AgentJob).where(and_(*conditions)))

    return BulkDeleteResult(deleted=count)


@router.delete("/{job_id}", status_code=204)
async def delete_agent_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    """Einzelnen abgeschlossenen oder fehlgeschlagenen Job löschen."""
    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    if job.status not in _DELETABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Nur abgeschlossene oder fehlgeschlagene Jobs können gelöscht werden (aktuell: {job.status})",
        )
    await db.delete(job)
