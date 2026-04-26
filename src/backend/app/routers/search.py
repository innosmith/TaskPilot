import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import Project, Tag, Task, User

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchTaskHit(BaseModel):
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    assignee: str
    is_completed: bool
    due_date: date | None


class SearchProjectHit(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    status: str


class SearchTagHit(BaseModel):
    id: uuid.UUID
    name: str
    color: str


class SearchResults(BaseModel):
    tasks: list[SearchTaskHit]
    projects: list[SearchProjectHit]
    tags: list[SearchTagHit]


@router.get("", response_model=SearchResults)
async def search(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SearchResults:
    pattern = f"%{q}%"

    task_result = await db.execute(
        select(Task, Project.name.label("project_name"))
        .join(Project, Task.project_id == Project.id)
        .where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
        .order_by(Task.updated_at.desc())
        .limit(20)
    )
    tasks = [
        SearchTaskHit(
            id=t.id, title=t.title, project_id=t.project_id,
            project_name=pname, assignee=t.assignee,
            is_completed=t.is_completed, due_date=t.due_date,
        )
        for t, pname in task_result.all()
    ]

    project_result = await db.execute(
        select(Project).where(Project.name.ilike(pattern)).order_by(Project.name).limit(10)
    )
    projects = [
        SearchProjectHit(id=p.id, name=p.name, color=p.color, status=p.status)
        for p in project_result.scalars().all()
    ]

    tag_result = await db.execute(
        select(Tag).where(Tag.name.ilike(pattern)).order_by(Tag.name).limit(10)
    )
    tags = [
        SearchTagHit(id=t.id, name=t.name, color=t.color)
        for t in tag_result.scalars().all()
    ]

    return SearchResults(tasks=tasks, projects=projects, tags=tags)
