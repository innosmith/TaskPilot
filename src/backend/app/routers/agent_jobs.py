import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import AgentJob, Task, User
from app.schemas import AgentJobCreate, AgentJobOut, AgentJobUpdate, AgentJobWithTask

router = APIRouter(prefix="/api/agent-jobs", tags=["agent-jobs"])


@router.get("", response_model=list[AgentJobWithTask])
async def list_agent_jobs(
    status: str | None = None,
    task_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AgentJobWithTask]:
    query = select(AgentJob, Task.title).join(Task, AgentJob.task_id == Task.id)
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
        .join(Task, AgentJob.task_id == Task.id)
        .where(AgentJob.id == job_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    job, title = row
    return AgentJobWithTask.model_validate({**job.__dict__, "task_title": title})


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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(job, field, value)

    if body.status == "running" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if body.status in ("completed", "failed") and job.completed_at is None:
        job.completed_at = datetime.now(timezone.utc)

    return job
