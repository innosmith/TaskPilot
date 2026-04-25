import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import BoardColumn, Project, Task, User
from app.schemas import (
    BoardColumnCreate,
    BoardColumnWithTasks,
    BoardOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    ProjectWithColumns,
    TaskCard,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectWithColumns])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ProjectWithColumns]:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.board_columns))
        .where(Project.status != "archived")
        .order_by(Project.priority.desc(), Project.name)
    )
    return result.scalars().all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProjectOut:
    project = Project(**body.model_dump())
    db.add(project)
    await db.flush()

    defaults = [
        BoardColumn(project_id=project.id, name="Open", color="#6B7280", position=1.0),
        BoardColumn(project_id=project.id, name="In Progress", color="#3B82F6", position=2.0),
        BoardColumn(project_id=project.id, name="Done", color="#10B981", position=3.0, is_archive=True),
    ]
    db.add_all(defaults)
    return project


@router.get("/{project_id}", response_model=ProjectWithColumns)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProjectWithColumns:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.board_columns))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProjectOut:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    return project


@router.get("/{project_id}/board", response_model=BoardOut)
async def get_board(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BoardOut:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.board_columns))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    columns_out = []
    for col in sorted(project.board_columns, key=lambda c: c.position):
        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.checklist_items))
            .where(Task.board_column_id == col.id, Task.is_completed == False)
            .order_by(Task.board_position)
        )
        tasks = task_result.scalars().all()

        task_cards = []
        for t in tasks:
            card = TaskCard(
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
            task_cards.append(card)

        columns_out.append(BoardColumnWithTasks(
            id=col.id,
            name=col.name,
            color=col.color,
            position=col.position,
            is_archive=col.is_archive,
            tasks=task_cards,
        ))

    return BoardOut(project=project, columns=columns_out)


@router.post("/{project_id}/columns", response_model=BoardColumnCreate, status_code=201)
async def create_column(
    project_id: uuid.UUID,
    body: BoardColumnCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BoardColumn:
    result = await db.execute(select(Project).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.position is None:
        max_result = await db.execute(
            select(BoardColumn.position)
            .where(BoardColumn.project_id == project_id)
            .order_by(BoardColumn.position.desc())
            .limit(1)
        )
        max_pos = max_result.scalar_one_or_none() or 0.0
        body.position = max_pos + 1.0

    col = BoardColumn(project_id=project_id, **body.model_dump())
    db.add(col)
    await db.flush()
    return col
