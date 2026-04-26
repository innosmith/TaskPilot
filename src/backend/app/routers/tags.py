import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import Tag, Task, TaskTag, User
from app.schemas import TagOut

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagCreateBody(BaseModel):
    name: str
    color: str = "#6B7280"


class TagUpdateBody(BaseModel):
    name: str | None = None
    color: str | None = None


@router.get("", response_model=list[TagOut])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[TagOut]:
    result = await db.execute(select(Tag).order_by(Tag.name))
    return result.scalars().all()


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TagOut:
    existing = await db.execute(select(Tag).where(Tag.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = Tag(name=body.name, color=body.color)
    db.add(tag)
    await db.flush()
    return tag


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TagOut:
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.execute(delete(Tag).where(Tag.id == tag_id))


@router.post("/tasks/{task_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_tag_to_task(
    task_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    if (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if (await db.execute(select(Tag).where(Tag.id == tag_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    existing = await db.execute(
        select(TaskTag).where(TaskTag.task_id == task_id, TaskTag.tag_id == tag_id)
    )
    if existing.scalar_one_or_none():
        return
    db.add(TaskTag(task_id=task_id, tag_id=tag_id))


@router.delete("/tasks/{task_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag_from_task(
    task_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    await db.execute(
        delete(TaskTag).where(TaskTag.task_id == task_id, TaskTag.tag_id == tag_id)
    )
