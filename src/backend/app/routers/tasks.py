import pathlib
import uuid
from datetime import date, datetime, timezone

import bleach
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import MEMBER_RESTRICTED_TASK_FIELDS, check_project_access, get_current_user, require_role
from app.routers.uploads import _scan_with_clamav
from app.database import get_db
from app.models import ActivityLog, AgentJob, Attachment, BoardColumn, BoardMember, ChecklistItem, Project, Task, User
from app.services.notification import notify_mentions, notify_task_assigned
from app.schemas import (
    AssigneeUser,
    ChecklistItemCreate,
    ChecklistItemOut,
    ChecklistItemUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)


async def _resolve_assignee_user(assignee: str, db: AsyncSession) -> AssigneeUser | None:
    """Löst eine assignee-UUID in ein AssigneeUser-Objekt auf."""
    if not assignee or assignee == "agent":
        return None
    try:
        uid = uuid.UUID(assignee)
    except ValueError:
        return None
    result = await db.execute(select(User).where(User.id == uid))
    u = result.scalar_one_or_none()
    if not u:
        return None
    return AssigneeUser(id=u.id, display_name=u.display_name, avatar_url=u.avatar_url)


def _resolve_assignee_input(assignee: str | None, user: User) -> str | None:
    """Wandelt 'me' in die User-UUID um."""
    if assignee == "me":
        return str(user.id)
    return assignee


async def _validate_assignee(
    assignee: str, project_id: uuid.UUID, db: AsyncSession,
) -> None:
    """Stellt sicher, dass ein UUID-Assignee BoardMember oder Owner ist."""
    if assignee in ("agent", "me"):
        return
    try:
        uid = uuid.UUID(assignee)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiger Assignee-Wert")
    owner_result = await db.execute(
        select(User).where(User.id == uid, User.role == "owner")
    )
    if owner_result.scalar_one_or_none() is not None:
        return
    result = await db.execute(
        select(BoardMember).where(
            BoardMember.project_id == project_id,
            BoardMember.user_id == uid,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400,
            detail="Zugewiesene Person ist kein Mitglied dieses Projekts",
        )

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _sanitize_text(text: str | None) -> str | None:
    if text is None:
        return None
    return bleach.clean(text, tags=[], strip=True)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> TaskOut:
    if user.role != "owner":
        if hasattr(body, "assignee") and body.assignee == "agent":
            raise HTTPException(status_code=403, detail="Agent-Zuweisung ist nicht erlaubt")
        for field in MEMBER_RESTRICTED_TASK_FIELDS:
            if hasattr(body, field):
                setattr(body, field, None)

    col_result = await db.execute(
        select(BoardColumn.project_id).where(BoardColumn.id == body.board_column_id)
    )
    project_id = col_result.scalar_one_or_none()
    if project_id and not await check_project_access(project_id, user, db):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Projekt")

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

    body.title = _sanitize_text(body.title) or body.title
    body.description = _sanitize_text(body.description)
    body.assignee = _resolve_assignee_input(body.assignee, user) or body.assignee
    if project_id:
        await _validate_assignee(body.assignee, project_id, db)

    task = Task(**body.model_dump())
    db.add(task)
    await db.flush()

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task.id)
    )
    task_obj = result.scalar_one()
    task_out = TaskOut.model_validate(task_obj)
    task_out.assignee_user = await _resolve_assignee_user(task_obj.assignee, db)
    return task_out


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


@router.get("/due-today")
async def list_due_today(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
):
    today = date.today()
    stmt = (
        select(Task)
        .where(
            Task.is_completed.is_(False),
            Task.due_date.isnot(None),
            Task.due_date <= today,
        )
        .options(selectinload(Task.tags))
        .order_by(Task.due_date)
        .limit(20)
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    project_ids = {t.project_id for t in tasks if t.project_id}
    project_names: dict[str, str] = {}
    if project_ids:
        pstmt = select(Project).where(Project.id.in_(project_ids))
        presult = await db.execute(pstmt)
        for p in presult.scalars().all():
            project_names[str(p.id)] = p.name

    return [
        {
            "id": str(t.id),
            "title": t.title,
            "project_id": str(t.project_id),
            "project_name": project_names.get(str(t.project_id), ""),
            "board_column_id": str(t.board_column_id),
            "board_position": t.board_position,
            "pipeline_column_id": str(t.pipeline_column_id) if t.pipeline_column_id else None,
            "pipeline_position": t.pipeline_position,
            "assignee": t.assignee,
            "due_date": t.due_date,
            "is_completed": t.is_completed,
            "is_pinned": t.is_pinned,
            "recurrence_rule": t.recurrence_rule,
            "template_id": str(t.template_id) if t.template_id else None,
            "tags": [{"id": str(tag.id), "name": tag.name, "color": tag.color} for tag in t.tags],
            "checklist_total": 0,
            "checklist_done": 0,
        }
        for t in tasks
    ]


@router.get("/pending-review", response_model=list[PendingReviewOut])
async def list_pending_review(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
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
    user: User = Depends(require_role("member")),
) -> TaskOut:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not await check_project_access(task.project_id, user, db):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Projekt")
    task_out = TaskOut.model_validate(task)
    task_out.assignee_user = await _resolve_assignee_user(task.assignee, db)
    return task_out


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> TaskOut:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.checklist_items))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if not await check_project_access(task.project_id, user, db):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Projekt")

    old_assignee = task.assignee
    update_data = body.model_dump(exclude_unset=True)

    if "assignee" in update_data:
        update_data["assignee"] = _resolve_assignee_input(update_data["assignee"], user)
        await _validate_assignee(update_data["assignee"], task.project_id, db)

    if user.role != "owner":
        for field in MEMBER_RESTRICTED_TASK_FIELDS:
            update_data.pop(field, None)
        if update_data.get("assignee") == "agent":
            raise HTTPException(status_code=403, detail="Agent-Zuweisung ist nicht erlaubt")

    if "title" in update_data:
        update_data["title"] = _sanitize_text(update_data["title"]) or update_data["title"]
    if "description" in update_data:
        update_data["description"] = _sanitize_text(update_data["description"])
    for field, value in update_data.items():
        setattr(task, field, value)

    if "due_date" in update_data and task.assignee != "agent" and task.pipeline_column_id:
        from app.services.pipeline_promoter import auto_place_task
        await auto_place_task(db, task)

    if body.assignee == "agent" and old_assignee != "agent" and user.role == "owner":
        job = AgentJob(task_id=task.id, llm_model=task.llm_override)
        db.add(job)

    new_assignee = task.assignee
    if new_assignee != old_assignee and new_assignee not in ("agent", "me"):
        try:
            new_uid = uuid.UUID(new_assignee)
            if new_uid != user.id:
                await notify_task_assigned(db, task, new_uid, user.email)
        except ValueError:
            pass

    task_out = TaskOut.model_validate(task)
    task_out.assignee_user = await _resolve_assignee_user(task.assignee, db)
    return task_out


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not await check_project_access(task.project_id, user, db):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Projekt")
    await db.delete(task)


@router.post("/{task_id}/confirm", response_model=TaskOut)
async def confirm_review_task(
    task_id: uuid.UUID,
    body: TaskConfirmBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
) -> TaskOut:
    """Task-Vorschlag bestätigen (setzt needs_review=False, erlaubt Änderungen)."""
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
    _user: User = Depends(require_role("member")),
) -> None:
    """Task-Vorschlag verwerfen (Task löschen)."""
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
    _user: User = Depends(require_role("member")),
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
    _user: User = Depends(require_role("member")),
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
    _user: User = Depends(require_role("member")),
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


@router.delete("/{task_id}/checklist/{item_id}", status_code=204)
async def delete_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
) -> None:
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.id == item_id, ChecklistItem.task_id == task_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    await db.delete(item)


@router.get("/{task_id}/recurrence")
async def get_recurrence_info(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
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
    """Konvertiert gängige Cron-Ausdrücke in lesbaren deutschen Text."""
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


# --- Activity Log ---

class ActivityLogOut(BaseModel):
    id: str
    task_id: str
    event_type: str
    actor: str
    details: dict | None
    created_at: str

class CommentCreate(BaseModel):
    text: str

class CommentUpdate(BaseModel):
    text: str

@router.get("/{task_id}/activity", response_model=list[ActivityLogOut])
async def list_activity(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
) -> list[ActivityLogOut]:
    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.task_id == task_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()
    return [
        ActivityLogOut(
            id=str(log.id),
            task_id=str(log.task_id),
            event_type=log.event_type,
            actor=log.actor,
            details=log.details,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post("/{task_id}/activity", response_model=ActivityLogOut, status_code=201)
async def add_comment(
    task_id: uuid.UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> ActivityLogOut:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    log = ActivityLog(
        task_id=task_id,
        event_type="comment",
        actor=user.email,
        details={"text": body.text},
    )
    db.add(log)
    await db.flush()

    await notify_mentions(db, body.text, task_id, task.title, user.email, user.id)

    return ActivityLogOut(
        id=str(log.id),
        task_id=str(log.task_id),
        event_type=log.event_type,
        actor=log.actor,
        details=log.details,
        created_at=log.created_at.isoformat(),
    )


@router.patch("/{task_id}/activity/{activity_id}", response_model=ActivityLogOut)
async def update_comment(
    task_id: uuid.UUID,
    activity_id: uuid.UUID,
    body: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> ActivityLogOut:
    result = await db.execute(select(Task).where(Task.id == task_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == activity_id,
            ActivityLog.task_id == task_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="Aktivitätseintrag nicht gefunden")
    if log.event_type != "comment":
        raise HTTPException(status_code=400, detail="Nur Kommentare können bearbeitet werden")
    if user.role != "owner" and log.actor != user.email:
        raise HTTPException(status_code=403, detail="Nur der Autor oder Owner darf Kommentare bearbeiten")

    sanitized = _sanitize_text(body.text) or body.text
    log.details = {"text": sanitized}
    return ActivityLogOut(
        id=str(log.id),
        task_id=str(log.task_id),
        event_type=log.event_type,
        actor=log.actor,
        details=log.details,
        created_at=log.created_at.isoformat(),
    )


@router.delete("/{task_id}/activity/{activity_id}")
async def delete_comment(
    task_id: uuid.UUID,
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> dict:
    result = await db.execute(select(Task).where(Task.id == task_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == activity_id,
            ActivityLog.task_id == task_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="Aktivitätseintrag nicht gefunden")
    if log.event_type != "comment":
        raise HTTPException(status_code=400, detail="Nur Kommentare können gelöscht werden")
    if user.role != "owner" and log.actor != user.email:
        raise HTTPException(status_code=403, detail="Nur der Autor oder Owner darf Kommentare löschen")

    await db.delete(log)
    return {"ok": True}


# --- Attachments ---

TASK_UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads" / "tasks"
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB

class AttachmentOut(BaseModel):
    id: str
    task_id: str
    filename: str
    filepath: str
    mime_type: str | None
    size: int
    uploaded_at: str


@router.get("/{task_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
) -> list[AttachmentOut]:
    result = await db.execute(
        select(Attachment)
        .where(Attachment.task_id == task_id)
        .order_by(Attachment.uploaded_at.desc())
    )
    attachments = result.scalars().all()
    base = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"
    out = []
    for a in attachments:
        full_path = base / a.filepath.lstrip("/").removeprefix("uploads/")
        size = full_path.stat().st_size if full_path.exists() else 0
        out.append(AttachmentOut(
            id=str(a.id), task_id=str(a.task_id), filename=a.filename,
            filepath=a.filepath, mime_type=a.mime_type, size=size,
            uploaded_at=a.uploaded_at.isoformat(),
        ))
    return out


@router.post("/{task_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    task_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> AttachmentOut:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not await check_project_access(task.project_id, user, db):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Projekt")

    data = await file.read()
    if len(data) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="Datei zu gross (max 10 MB)")

    if not await _scan_with_clamav(data):
        raise HTTPException(status_code=422, detail="Datei wurde als schädlich erkannt")

    task_dir = TASK_UPLOADS_DIR / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (file.filename or "datei").replace("/", "_").replace("\\", "_")
    ext = pathlib.Path(safe_name).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = task_dir / stored_name
    dest.write_bytes(data)

    relative_path = f"/uploads/tasks/{task_id}/{stored_name}"
    attachment = Attachment(
        task_id=task_id,
        filename=safe_name,
        filepath=relative_path,
        mime_type=file.content_type,
    )
    db.add(attachment)
    await db.flush()

    return AttachmentOut(
        id=str(attachment.id), task_id=str(attachment.task_id),
        filename=attachment.filename, filepath=attachment.filepath,
        mime_type=attachment.mime_type, size=len(data),
        uploaded_at=attachment.uploaded_at.isoformat(),
    )


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("member")),
) -> None:
    result = await db.execute(
        select(Attachment)
        .where(Attachment.id == attachment_id, Attachment.task_id == task_id)
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if not attachment.filepath.startswith("onedrive://"):
        base = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"
        full_path = base / attachment.filepath.lstrip("/").removeprefix("uploads/")
        if full_path.exists():
            full_path.unlink()

    await db.delete(attachment)


class OneDriveAttachBody(BaseModel):
    item_id: str
    name: str


@router.post("/{task_id}/attachments/onedrive", response_model=AttachmentOut, status_code=201)
async def add_onedrive_attachment(
    task_id: uuid.UUID,
    body: OneDriveAttachBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("owner")),
) -> AttachmentOut:
    """Speichert eine OneDrive-Dateireferenz als Attachment (keine lokale Kopie)."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    mime_ext = body.name.rsplit(".", 1)[-1].lower() if "." in body.name else None
    mime_map = {
        "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain", "csv": "text/csv", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    }
    mime_type = mime_map.get(mime_ext or "", "application/octet-stream")

    attachment = Attachment(
        task_id=task_id,
        filename=body.name,
        filepath=f"onedrive://{body.item_id}",
        mime_type=mime_type,
    )
    db.add(attachment)
    await db.flush()

    return AttachmentOut(
        id=str(attachment.id), task_id=str(attachment.task_id),
        filename=attachment.filename, filepath=attachment.filepath,
        mime_type=attachment.mime_type, size=0,
        uploaded_at=attachment.uploaded_at.isoformat(),
    )
