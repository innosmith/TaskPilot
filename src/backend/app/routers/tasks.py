import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import BoardColumn, ChecklistItem, Task, User
from app.schemas import (
    ChecklistItemCreate,
    ChecklistItemOut,
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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
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
