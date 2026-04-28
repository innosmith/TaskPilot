import uuid
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select, update
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
    """Bulk-Löschung von abgeschlossenen/fehlgeschlagenen Jobs.
    
    status=stale setzt running-Jobs > 30 Min auf failed und gibt die Anzahl zurück.
    """
    if status == "stale":
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        count_result = await db.execute(
            select(func.count())
            .where(and_(AgentJob.status == "running", AgentJob.started_at < cutoff))
            .select_from(AgentJob)
        )
        count = count_result.scalar_one()
        if count > 0:
            await db.execute(
                update(AgentJob)
                .where(and_(AgentJob.status == "running", AgentJob.started_at < cutoff))
                .values(
                    status="failed",
                    error_message="Manuell als hängend markiert",
                    completed_at=datetime.now(timezone.utc),
                )
            )
        return BulkDeleteResult(deleted=count)

    if status == "both":
        status_filter = AgentJob.status.in_(list(_DELETABLE_STATUSES))
    elif status in _DELETABLE_STATUSES:
        status_filter = AgentJob.status == status
    else:
        raise HTTPException(status_code=400, detail="status muss 'completed', 'failed', 'both' oder 'stale' sein")

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
    """Einzelnen Job löschen (completed/failed) oder abbrechen (running/queued)."""
    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    if job.status in _DELETABLE_STATUSES:
        await db.delete(job)
    elif job.status in ("running", "queued"):
        job.status = "failed"
        job.error_message = "Manuell abgebrochen"
        job.completed_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(
            status_code=409,
            detail=f"Job im Status '{job.status}' kann nicht gelöscht/abgebrochen werden",
        )


@router.get("/{job_id}/trace")
async def get_agent_job_trace(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Session-Trace eines Agent-Jobs: Tool-Aufrufe, Reasoning, Fehler."""
    from pathlib import Path

    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")

    sessions_dir = Path.home() / ".nanobot" / "workspace" / "sessions"
    prefix = f"{job.job_type or 'generic'}_{job_id}_"
    session_file = None
    if sessions_dir.exists():
        for f in sorted(sessions_dir.glob(f"{prefix}*.jsonl"), reverse=True):
            session_file = f
            break

    if not session_file or not session_file.exists():
        return {
            "job_id": str(job_id),
            "status": job.status,
            "session_found": False,
            "steps": [],
        }

    steps = []
    metadata = {}
    try:
        with open(session_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("_type") == "metadata":
                    metadata = entry
                    continue

                role = entry.get("role")
                if role == "assistant":
                    tool_calls = entry.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            args_str = fn.get("arguments", "{}")
                            try:
                                args = json.loads(args_str)
                                args_summary = {k: str(v)[:120] for k, v in args.items()}
                            except (json.JSONDecodeError, AttributeError):
                                args_summary = {"raw": args_str[:200]}
                            steps.append({
                                "type": "tool_call",
                                "tool": fn.get("name", "?"),
                                "call_id": tc.get("id"),
                                "arguments": args_summary,
                            })
                    reasoning = entry.get("reasoning_content")
                    content = entry.get("content", "")
                    if reasoning:
                        steps.append({
                            "type": "reasoning",
                            "text": reasoning[:500],
                        })
                    if content and not tool_calls:
                        steps.append({
                            "type": "assistant_message",
                            "text": content[:800],
                        })

                elif role == "tool":
                    tool_content = entry.get("content", "")
                    is_error = "Fehler:" in tool_content or "Error" in tool_content[:50]
                    steps.append({
                        "type": "tool_result",
                        "call_id": entry.get("tool_call_id"),
                        "tool_name": entry.get("name", "?"),
                        "chars": len(tool_content),
                        "is_error": is_error,
                        "preview": tool_content[:300] if is_error else tool_content[:150],
                    })
    except Exception as e:
        return {
            "job_id": str(job_id),
            "status": job.status,
            "session_found": True,
            "parse_error": str(e),
            "steps": [],
        }

    created = metadata.get("created_at")
    updated = metadata.get("updated_at")
    duration_s = None
    if created and updated:
        try:
            from datetime import datetime as _dt
            t0 = _dt.fromisoformat(created)
            t1 = _dt.fromisoformat(updated)
            duration_s = round((t1 - t0).total_seconds(), 1)
        except Exception:
            pass

    tool_calls = [s for s in steps if s["type"] == "tool_call"]
    tool_results = [s for s in steps if s["type"] == "tool_result"]
    errors = [s for s in tool_results if s.get("is_error")]

    return {
        "job_id": str(job_id),
        "status": job.status,
        "session_found": True,
        "session_file": session_file.name,
        "duration_seconds": duration_s,
        "summary": {
            "total_tool_calls": len(tool_calls),
            "total_tool_results": len(tool_results),
            "errors": len(errors),
            "tools_used": list(dict.fromkeys(tc["tool"] for tc in tool_calls)),
        },
        "steps": steps,
    }
