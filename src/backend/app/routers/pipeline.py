from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import PipelineColumn, Task, User
from app.schemas import PipelineColumnWithTasks, PipelineOut, TaskCard

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
            position=col.position,
            column_type=col.column_type,
            tasks=task_cards,
        ))

    return PipelineOut(columns=columns_out)
