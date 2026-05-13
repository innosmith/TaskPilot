"""Notification-Router: CRUD für In-App-Notifications."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_role
from app.database import get_db
from app.models import BoardMember, Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str | None
    link: str | None
    source_type: str | None
    source_id: str | None
    is_read: bool
    created_at: str


class UnreadCountOut(BaseModel):
    count: int


class MentionableUserOut(BaseModel):
    id: str
    display_name: str
    avatar_url: str | None


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    result = await db.execute(stmt)
    return [
        NotificationOut(
            id=str(n.id),
            type=n.type,
            title=n.title,
            body=n.body,
            link=n.link,
            source_type=n.source_type,
            source_id=str(n.source_id) if n.source_id else None,
            is_read=n.is_read,
            created_at=n.created_at.isoformat(),
        )
        for n in result.scalars().all()
    ]


@router.get("/unread-count", response_model=UnreadCountOut)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
    )
    return UnreadCountOut(count=result.scalar() or 0)


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification nicht gefunden")
    notif.is_read = True
    return {"ok": True}


@router.post("/read-all")
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    return {"ok": True}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification nicht gefunden")
    await db.delete(notif)
    return {"ok": True}


@router.get("/mentionable-users", response_model=list[MentionableUserOut])
async def get_mentionable_users(
    project_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> list[MentionableUserOut]:
    """Gibt alle Users zurück, die in einem Projekt erwähnt werden können (Members + Owner)."""
    owner_result = await db.execute(
        select(User).where(User.role == "owner", User.is_active.is_(True))
    )
    owners = list(owner_result.scalars().all())

    member_result = await db.execute(
        select(User)
        .join(BoardMember, BoardMember.user_id == User.id)
        .where(BoardMember.project_id == project_id, User.is_active.is_(True))
    )
    members = list(member_result.scalars().all())

    seen = set()
    result = []
    for u in owners + members:
        if u.id in seen:
            continue
        seen.add(u.id)
        result.append(MentionableUserOut(
            id=str(u.id),
            display_name=u.display_name,
            avatar_url=u.avatar_url,
        ))
    return result
