import secrets
import uuid
from datetime import datetime, timezone

import logging

import bcrypt
import bleach
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import check_project_access, require_owner, require_role
from app.database import get_db
from app.models import (
    BoardColumn,
    BoardMember,
    Mindmap,
    MindmapFolder,
    MindmapShare,
    Project,
    Task,
    User,
)
from app.schemas import (
    ConvertToTasksRequest,
    ConvertToTasksResponse,
    MindmapCreate,
    MindmapFolderCreate,
    MindmapFolderOut,
    MindmapFolderUpdate,
    MindmapListItem,
    MindmapOut,
    MindmapShareCreate,
    MindmapShareOut,
    MindmapUpdate,
    ShareVerifyRequest,
)
from app.services.freemind_parser import extract_title, parse_freemind_xml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mindmaps", tags=["mindmaps"])
public_router = APIRouter(prefix="/api/public/mindmaps", tags=["mindmaps-public"])


def _default_flow_data(title: str) -> dict:
    return {
        "nodes": [
            {
                "id": "root",
                "type": "mindmapNode",
                "position": {"x": 0, "y": 0},
                "data": {"label": title},
            }
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


# ---------------------------------------------------------------------------
# FreeMind .mm Import (Owner-only)
# ---------------------------------------------------------------------------

MAX_IMPORT_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=MindmapOut, status_code=status.HTTP_201_CREATED)
async def import_mindmap(
    file: UploadFile,
    folder_id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapOut:
    """FreeMind .mm Datei importieren und als Mind-Map erstellen."""
    if not file.filename or not file.filename.lower().endswith(".mm"):
        raise HTTPException(
            status_code=400,
            detail="Nur FreeMind .mm Dateien werden unterstützt",
        )

    raw = await file.read()
    if len(raw) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="Datei zu gross (max. 10 MB)")

    try:
        title = bleach.clean(extract_title(raw))
        flow_data = parse_freemind_xml(raw)
    except Exception as exc:
        logger.warning("FreeMind-Import fehlgeschlagen: %s", exc)
        raise HTTPException(
            status_code=422,
            detail=f"Datei konnte nicht geparst werden: {exc}",
        )

    if folder_id:
        folder = await db.get(MindmapFolder, folder_id)
        if not folder or folder.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Ordner nicht gefunden")

    mindmap = Mindmap(
        title=title,
        folder_id=folder_id,
        owner_id=user.id,
        visibility="private",
        flow_data=flow_data,
        settings={},
    )
    db.add(mindmap)
    await db.flush()
    await db.refresh(mindmap)
    return mindmap


# ---------------------------------------------------------------------------
# Folder CRUD (Owner-only)
# ---------------------------------------------------------------------------

@router.get("/folders", response_model=list[MindmapFolderOut])
async def list_folders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[MindmapFolderOut]:
    result = await db.execute(
        select(MindmapFolder)
        .where(MindmapFolder.owner_id == user.id)
        .order_by(MindmapFolder.position)
    )
    return result.scalars().all()


@router.post("/folders", response_model=MindmapFolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: MindmapFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapFolderOut:
    if body.parent_id:
        parent = await db.get(MindmapFolder, body.parent_id)
        if not parent or parent.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Übergeordneter Ordner nicht gefunden")

    folder = MindmapFolder(**body.model_dump(), owner_id=user.id)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.patch("/folders/{folder_id}", response_model=MindmapFolderOut)
async def update_folder(
    folder_id: uuid.UUID,
    body: MindmapFolderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapFolderOut:
    folder = await db.get(MindmapFolder, folder_id)
    if not folder or folder.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Ordner nicht gefunden")

    updates = body.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"]:
        if updates["parent_id"] == folder_id:
            raise HTTPException(status_code=400, detail="Ordner kann nicht sein eigener Elternordner sein")
        parent = await db.get(MindmapFolder, updates["parent_id"])
        if not parent or parent.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Übergeordneter Ordner nicht gefunden")

    for key, value in updates.items():
        setattr(folder, key, value)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> None:
    folder = await db.get(MindmapFolder, folder_id)
    if not folder or folder.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Ordner nicht gefunden")
    await db.delete(folder)
    await db.flush()


# ---------------------------------------------------------------------------
# Mind-Map CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[MindmapListItem])
async def list_mindmaps(
    folder_id: uuid.UUID | None = Query(None),
    project_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> list[MindmapListItem]:
    share_count_sub = (
        select(func.count(MindmapShare.id))
        .where(MindmapShare.mindmap_id == Mindmap.id)
        .correlate(Mindmap)
        .scalar_subquery()
    )

    q = (
        select(
            Mindmap,
            Project.name.label("project_name"),
            share_count_sub.label("share_count"),
        )
        .outerjoin(Project, Mindmap.project_id == Project.id)
    )

    if user.role == "owner":
        q = q.where(Mindmap.owner_id == user.id)
    else:
        accessible_projects = select(BoardMember.project_id).where(BoardMember.user_id == user.id)
        q = q.where(
            Mindmap.visibility.in_(["project", "shared"]),
            Mindmap.project_id.in_(accessible_projects),
        )

    if folder_id is not None:
        q = q.where(Mindmap.folder_id == folder_id)
    if project_id is not None:
        q = q.where(Mindmap.project_id == project_id)

    q = q.order_by(Mindmap.updated_at.desc())
    result = await db.execute(q)

    items = []
    for row in result.all():
        mindmap = row[0]
        item = MindmapListItem.model_validate(mindmap)
        item.project_name = row.project_name
        item.share_count = row.share_count or 0
        items.append(item)
    return items


@router.post("", response_model=MindmapOut, status_code=status.HTTP_201_CREATED)
async def create_mindmap(
    body: MindmapCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapOut:
    if body.visibility == "project" and not body.project_id:
        raise HTTPException(
            status_code=400,
            detail="Für Sichtbarkeit 'project' muss eine Projekt-ID angegeben werden",
        )

    if body.project_id:
        project = await db.get(Project, body.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if body.folder_id:
        folder = await db.get(MindmapFolder, body.folder_id)
        if not folder or folder.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Ordner nicht gefunden")

    data = body.model_dump()
    if not data.get("flow_data"):
        data["flow_data"] = _default_flow_data(body.title)
    if not data.get("settings"):
        data["settings"] = {}

    mindmap = Mindmap(**data, owner_id=user.id)
    db.add(mindmap)
    await db.flush()
    await db.refresh(mindmap)
    return mindmap


@router.get("/{mindmap_id}", response_model=MindmapOut)
async def get_mindmap(
    mindmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> MindmapOut:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    if user.role == "owner":
        if mindmap.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")
    else:
        if mindmap.visibility not in ("project", "shared"):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Mind-Map")
        if mindmap.project_id and not await check_project_access(mindmap.project_id, user, db):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Mind-Map")

    return mindmap


@router.patch("/{mindmap_id}", response_model=MindmapOut)
async def update_mindmap(
    mindmap_id: uuid.UUID,
    body: MindmapUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("member")),
) -> MindmapOut:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    if user.role == "owner":
        if mindmap.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")
    else:
        if mindmap.visibility not in ("project", "shared"):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Mind-Map")
        if mindmap.project_id and not await check_project_access(mindmap.project_id, user, db):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Mind-Map")

    updates = body.model_dump(exclude_unset=True)

    if "title" in updates and updates["title"]:
        updates["title"] = bleach.clean(updates["title"])

    if updates.get("visibility") == "project" and not (updates.get("project_id") or mindmap.project_id):
        raise HTTPException(
            status_code=400,
            detail="Für Sichtbarkeit 'project' muss eine Projekt-ID angegeben werden",
        )

    for key, value in updates.items():
        setattr(mindmap, key, value)
    await db.flush()
    await db.refresh(mindmap)
    return mindmap


@router.delete("/{mindmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mindmap(
    mindmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> None:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap or mindmap.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")
    await db.delete(mindmap)
    await db.flush()


@router.post("/{mindmap_id}/duplicate", response_model=MindmapOut, status_code=status.HTTP_201_CREATED)
async def duplicate_mindmap(
    mindmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapOut:
    original = await db.get(Mindmap, mindmap_id)
    if not original or original.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    copy = Mindmap(
        title=f"{original.title} (Kopie)",
        folder_id=original.folder_id,
        project_id=original.project_id,
        owner_id=user.id,
        visibility=original.visibility,
        flow_data=original.flow_data,
        settings=original.settings,
        background_url=original.background_url,
        background_color=original.background_color,
        thumbnail_url=original.thumbnail_url,
        is_template=original.is_template,
    )
    db.add(copy)
    await db.flush()
    await db.refresh(copy)
    return copy


# ---------------------------------------------------------------------------
# Task Conversion (Owner-only)
# ---------------------------------------------------------------------------

@router.post("/{mindmap_id}/convert-to-tasks", response_model=ConvertToTasksResponse)
async def convert_to_tasks(
    mindmap_id: uuid.UUID,
    body: ConvertToTasksRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> ConvertToTasksResponse:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap or mindmap.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    project = await db.get(Project, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    column = await db.get(BoardColumn, body.board_column_id)
    if not column or column.project_id != body.project_id:
        raise HTTPException(status_code=404, detail="Board-Spalte nicht gefunden oder gehört nicht zum Projekt")

    flow_data = mindmap.flow_data or {}
    nodes = flow_data.get("nodes", [])
    node_map = {n["id"]: n for n in nodes if isinstance(n, dict) and "id" in n}

    max_result = await db.execute(
        select(Task.board_position)
        .where(Task.board_column_id == body.board_column_id)
        .order_by(Task.board_position.desc())
        .limit(1)
    )
    current_pos = (max_result.scalar_one_or_none() or 0.0) + 1.0

    created_ids: list[uuid.UUID] = []
    for node_id in body.node_ids:
        node = node_map.get(node_id)
        if not node:
            continue
        data = node.get("data", {})
        label = data.get("label", "Unbenannt")
        notes = data.get("notes", "")
        url = data.get("url", "")

        description_parts = []
        if notes:
            description_parts.append(notes)
        if url:
            description_parts.append(f"Link: {url}")

        task = Task(
            title=bleach.clean(label),
            description="\n".join(description_parts) if description_parts else None,
            project_id=body.project_id,
            board_column_id=body.board_column_id,
            board_position=current_pos,
        )
        db.add(task)
        await db.flush()
        created_ids.append(task.id)
        current_pos += 1.0

    return ConvertToTasksResponse(created_task_ids=created_ids, count=len(created_ids))


# ---------------------------------------------------------------------------
# Share Management (Owner-only)
# ---------------------------------------------------------------------------

@router.post("/{mindmap_id}/shares", response_model=MindmapShareOut, status_code=status.HTTP_201_CREATED)
async def create_share(
    mindmap_id: uuid.UUID,
    body: MindmapShareCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> MindmapShareOut:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap or mindmap.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    token = secrets.token_urlsafe(32)

    share = MindmapShare(
        mindmap_id=mindmap_id,
        token=token,
        password_hash=password_hash,
        permission=body.permission,
        label=body.label,
        expires_at=body.expires_at,
    )
    db.add(share)

    if mindmap.visibility != "shared":
        mindmap.visibility = "shared"

    await db.flush()
    await db.refresh(share)
    return share


@router.get("/{mindmap_id}/shares", response_model=list[MindmapShareOut])
async def list_shares(
    mindmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[MindmapShareOut]:
    mindmap = await db.get(Mindmap, mindmap_id)
    if not mindmap or mindmap.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    result = await db.execute(
        select(MindmapShare)
        .where(MindmapShare.mindmap_id == mindmap_id)
        .order_by(MindmapShare.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(
    share_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> None:
    share = await db.get(MindmapShare, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share nicht gefunden")

    mindmap = await db.get(Mindmap, share.mindmap_id)
    if not mindmap or mindmap.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Share nicht gefunden")

    await db.delete(share)
    await db.flush()


# ---------------------------------------------------------------------------
# Public Access (no auth)
# ---------------------------------------------------------------------------

async def _verify_share(
    token: str, password: str, db: AsyncSession
) -> MindmapShare:
    """Prüft Token und Passwort, gibt das Share-Objekt zurück."""
    result = await db.execute(
        select(MindmapShare).where(MindmapShare.token == token)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Ungültiger Share-Link")

    if share.expires_at and share.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Dieser Share-Link ist abgelaufen")

    if not bcrypt.checkpw(password.encode(), share.password_hash.encode()):
        raise HTTPException(status_code=403, detail="Falsches Passwort")

    share.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return share


@public_router.post("/{token}/verify")
async def verify_share(
    token: str,
    body: ShareVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    share = await _verify_share(token, body.password, db)
    return {
        "valid": True,
        "permission": share.permission,
        "mindmap_id": share.mindmap_id,
    }


@public_router.get("/{token}", response_model=MindmapOut)
async def get_public_mindmap(
    token: str,
    db: AsyncSession = Depends(get_db),
    x_share_password: str = Header(..., alias="X-Share-Password"),
) -> MindmapOut:
    share = await _verify_share(token, x_share_password, db)
    mindmap = await db.get(Mindmap, share.mindmap_id)
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")
    return mindmap


@public_router.patch("/{token}", response_model=MindmapOut)
async def update_public_mindmap(
    token: str,
    body: MindmapUpdate,
    db: AsyncSession = Depends(get_db),
    x_share_password: str = Header(..., alias="X-Share-Password"),
) -> MindmapOut:
    share = await _verify_share(token, x_share_password, db)
    if share.permission != "edit":
        raise HTTPException(status_code=403, detail="Nur Lesezugriff für diesen Share-Link")

    mindmap = await db.get(Mindmap, share.mindmap_id)
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mind-Map nicht gefunden")

    updates = body.model_dump(exclude_unset=True)
    allowed_fields = {"flow_data", "settings"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}

    for key, value in filtered.items():
        setattr(mindmap, key, value)
    await db.flush()
    await db.refresh(mindmap)
    return mindmap
