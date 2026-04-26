import uuid
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import AgentJob, BoardColumn, ChecklistItem, Project, Task, User
from app.schemas import (
    ChecklistItemCreate,
    ChecklistItemOut,
    ChecklistItemUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TaskOut:
    if body.board_position is None:
        max_result = await db.execute(
            select(Task.board_position)
            .where(Task.board_column_id == body.board_column_id)
            .order_by(Task.board_position.desc())
            .limit(1)
        )
        max_pos = max_result.scalar_one_or_none() or 0.0
        body.board_position = max_pos + 1.0

    if body.pipeline_column_id and body.pipeline_position is None:
        max_result = await db.execute(
            select(Task.pipeline_position)
            .where(Task.pipeline_column_id == body.pipeline_column_id)
            .order_by(Task.pipeline_position.desc())
            .limit(1)
        )
        max_pos = max_result.scalar_one_or_none() or 0.0
        body.pipeline_position = max_pos + 1.0

    task = Task(**body.model_dump())
    db.add(task)
    await db.flush()

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task.id)
    )
    return result.scalar_one()


# --- Pending Review (auto-erstellte Tasks aus E-Mail-Triage) ---

class PendingReviewOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    project_id: uuid.UUID
    project_name: str
    board_column_id: uuid.UUID
    pipeline_column_id: uuid.UUID | None
    due_date: str | None
    email_message_id: str | None
    created_at: str


class TaskConfirmBody(BaseModel):
    title: str | None = None
    project_id: uuid.UUID | None = None
    board_column_id: uuid.UUID | None = None


@router.get("/pending-review", response_model=list[PendingReviewOut])
async def list_pending_review(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PendingReviewOut]:
    """Tasks mit needs_review=True laden (auto-erstellte Task-Vorschlaege)."""
    result = await db.execute(
        select(Task, Project.name)
        .join(Project, Task.project_id == Project.id)
        .where(Task.needs_review == True)  # noqa: E712
        .order_by(Task.created_at.desc())
    )
    rows = result.all()
    return [
        PendingReviewOut(
            id=task.id,
            title=task.title,
            description=task.description,
            project_id=task.project_id,
            project_name=proj_name,
            board_column_id=task.board_column_id,
            pipeline_column_id=task.pipeline_column_id,
            due_date=task.due_date.isoformat() if task.due_date else None,
            email_message_id=task.email_message_id,
            created_at=task.created_at.isoformat(),
        )
        for task, proj_name in rows
    ]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TaskOut:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TaskOut:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    old_assignee = task.assignee
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    if body.assignee == "agent" and old_assignee != "agent":
        job = AgentJob(task_id=task.id, llm_model=task.llm_override)
        db.add(job)

    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)


@router.post("/{task_id}/confirm", response_model=TaskOut)
async def confirm_review_task(
    task_id: uuid.UUID,
    body: TaskConfirmBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TaskOut:
    """Task-Vorschlag bestaetigen (setzt needs_review=False, erlaubt Aenderungen)."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.needs_review:
        raise HTTPException(status_code=409, detail="Task ist bereits bestaetigt")

    task.needs_review = False

    if body.title is not None:
        task.title = body.title
    if body.project_id is not None:
        task.project_id = body.project_id
        if body.board_column_id is not None:
            task.board_column_id = body.board_column_id
        else:
            col_result = await db.execute(
                select(BoardColumn)
                .where(BoardColumn.project_id == body.project_id)
                .order_by(BoardColumn.position)
                .limit(1)
            )
            first_col = col_result.scalar_one_or_none()
            if first_col:
                task.board_column_id = first_col.id

    return task


@router.post("/{task_id}/dismiss-review", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_review_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    """Task-Vorschlag verwerfen (Task loeschen)."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.needs_review:
        raise HTTPException(status_code=409, detail="Nur unbestaetigte Vorschlaege koennen verworfen werden")
    await db.delete(task)


# --- Checklist ---

@router.get("/{task_id}/checklist", response_model=list[ChecklistItemOut])
async def list_checklist(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ChecklistItemOut]:
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.task_id == task_id)
        .order_by(ChecklistItem.position)
    )
    return result.scalars().all()


@router.post("/{task_id}/checklist", response_model=ChecklistItemOut, status_code=201)
async def add_checklist_item(
    task_id: uuid.UUID,
    body: ChecklistItemCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChecklistItemOut:
    if body.position is None:
        max_result = await db.execute(
            select(ChecklistItem.position)
            .where(ChecklistItem.task_id == task_id)
            .order_by(ChecklistItem.position.desc())
            .limit(1)
        )
        max_pos = max_result.scalar_one_or_none() or 0.0
        body.position = max_pos + 1.0

    item = ChecklistItem(task_id=task_id, **body.model_dump())
    db.add(item)
    await db.flush()
    return item


@router.patch("/{task_id}/checklist/{item_id}", response_model=ChecklistItemOut)
async def update_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistItemUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChecklistItemOut:
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.id == item_id, ChecklistItem.task_id == task_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    return item


@router.get("/{task_id}/recurrence")
async def get_recurrence_info(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Gibt Wiederholungsinformationen zurück: nächstes Auftreten,
    letzte Instanz und menschenlesbarer Cron-Text."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.recurrence_rule:
        return {"recurrence_rule": None, "next_occurrence": None, "description": None}

    if not croniter.is_valid(task.recurrence_rule):
        return {
            "recurrence_rule": task.recurrence_rule,
            "next_occurrence": None,
            "description": "Ungueltige Cron-Expression",
        }

    now = datetime.now(timezone.utc)
    cron = croniter(task.recurrence_rule, now)
    next_run = cron.get_next(datetime)

    description = _cron_to_human(task.recurrence_rule)

    return {
        "recurrence_rule": task.recurrence_rule,
        "next_occurrence": next_run.isoformat(),
        "description": description,
    }


def _cron_to_human(cron_expr: str) -> str:
    """Konvertiert gaengige Cron-Ausdruecke in lesbaren deutschen Text."""
    presets = {
        "0 0 * * *": "Taeglich um Mitternacht",
        "0 7 * * *": "Taeglich um 07:00",
        "0 8 * * *": "Taeglich um 08:00",
        "0 9 * * *": "Taeglich um 09:00",
        "0 7 * * MON": "Jeden Montag um 07:00",
        "0 7 * * 1": "Jeden Montag um 07:00",
        "0 8 * * MON": "Jeden Montag um 08:00",
        "0 8 * * 1": "Jeden Montag um 08:00",
        "0 9 * * MON": "Jeden Montag um 09:00",
        "0 9 * * 1": "Jeden Montag um 09:00",
        "0 7 * * MON-FRI": "Werktags um 07:00",
        "0 7 * * 1-5": "Werktags um 07:00",
        "0 8 1 * *": "Monatlich am 1. um 08:00",
        "0 9 1 * *": "Monatlich am 1. um 09:00",
        "0 8 15 * *": "Monatlich am 15. um 08:00",
    }
    if cron_expr in presets:
        return presets[cron_expr]

    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, dom, month, dow = parts

    time_str = ""
    if hour != "*" and minute != "*":
        time_str = f" um {hour.zfill(2)}:{minute.zfill(2)}"

    if dom == "*" and dow == "*":
        return f"Taeglich{time_str}"
    if dom == "*" and dow != "*":
        day_names = {
            "0": "Sonntag", "SUN": "Sonntag",
            "1": "Montag", "MON": "Montag",
            "2": "Dienstag", "TUE": "Dienstag",
            "3": "Mittwoch", "WED": "Mittwoch",
            "4": "Donnerstag", "THU": "Donnerstag",
            "5": "Freitag", "FRI": "Freitag",
            "6": "Samstag", "SAT": "Samstag",
        }
        day = day_names.get(dow.upper(), dow)
        return f"Jeden {day}{time_str}"
    if dow == "*" and dom != "*":
        return f"Monatlich am {dom}.{time_str}"

    return cron_expr
