from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import PipelineColumn, Task, User
from app.schemas import PipelineColumnOut, PipelineColumnUpdate, PipelineColumnWithTasks, PipelineOut, TaskCard

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("", response_model=PipelineOut)
async def get_pipeline(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PipelineOut:
    col_result = await db.execute(
        select(PipelineColumn).order_by(PipelineColumn.position)
    )
    columns = col_result.scalars().all()

    columns_out = []
    for col in columns:
        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.checklist_items))
            .where(Task.pipeline_column_id == col.id, Task.is_completed == False)
            .order_by(Task.pipeline_position)
        )
        tasks = task_result.scalars().all()

        task_cards = [
            TaskCard(
                id=t.id,
                title=t.title,
                project_id=t.project_id,
                board_column_id=t.board_column_id,
                board_position=t.board_position,
                pipeline_column_id=t.pipeline_column_id,
                pipeline_position=t.pipeline_position,
                assignee=t.assignee,
                due_date=t.due_date,
                is_completed=t.is_completed,
                is_pinned=t.is_pinned,
                tags=t.tags,
                checklist_total=len(t.checklist_items),
                checklist_done=sum(1 for ci in t.checklist_items if ci.is_checked),
            )
            for t in tasks
        ]

        columns_out.append(PipelineColumnWithTasks(
            id=col.id,
            name=col.name,
            color=col.color,
            icon_emoji=col.icon_emoji,
            position=col.position,
            column_type=col.column_type,
            tasks=task_cards,
        ))

    return PipelineOut(columns=columns_out)


class PipelineColumnCreate(BaseModel):
    name: str
    color: str | None = None
    icon_emoji: str | None = None
    position: float | None = None


@router.post("/columns", response_model=PipelineColumnOut, status_code=201)
async def create_pipeline_column(
    body: PipelineColumnCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PipelineColumn:
    if body.position is None:
        max_result = await db.execute(
            select(PipelineColumn.position).order_by(PipelineColumn.position.desc()).limit(1)
        )
        max_pos = max_result.scalar_one_or_none() or 0.0
        body.position = max_pos + 1.0
    col = PipelineColumn(name=body.name, color=body.color, icon_emoji=body.icon_emoji, position=body.position)
    db.add(col)
    await db.flush()
    return col


@router.patch("/columns/{col_id}", response_model=PipelineColumnOut)
async def update_pipeline_column(
    col_id: str,
    body: PipelineColumnUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PipelineColumn:
    result = await db.execute(select(PipelineColumn).where(PipelineColumn.id == col_id))
    col = result.scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=404, detail="Pipeline column not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(col, field, value)
    return col


@router.delete("/columns/{col_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline_column(
    col_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(select(PipelineColumn).where(PipelineColumn.id == col_id))
    col = result.scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=404, detail="Pipeline column not found")
    await db.delete(col)
