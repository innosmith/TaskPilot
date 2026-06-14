from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_role
from app.models import User
from app.services.hermes_config import get_hermes_home

router = APIRouter(prefix="/api/memory", tags=["memory"])

# Hermes-Home: memories/, skills/, SOUL.md, config.yaml
HERMES_HOME = get_hermes_home()


class MemoryFile(BaseModel):
    name: str
    content: str
    size: int


@router.get("", response_model=list[MemoryFile])
async def list_memory_files(
    _user: User = Depends(require_role("owner")),
) -> list[MemoryFile]:
    memory_dir = HERMES_HOME / "memories"
    if not memory_dir.exists():
        return []

    files = []
    for f in sorted(memory_dir.iterdir()):
        # Obsolete Migrations-Archive (z.B. history-nanobot-import.jsonl) ausblenden:
        # werden zur Laufzeit nicht geladen und verstopfen nur die Intelligenz-Ansicht.
        if f.name.endswith("-import.jsonl"):
            continue
        if f.is_file() and f.suffix in (".md", ".jsonl", ".txt"):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                files.append(MemoryFile(name=f.name, content=content[:50000], size=f.stat().st_size))
            except OSError:
                continue
    return files


@router.get("/{filename}", response_model=MemoryFile)
async def get_memory_file(
    filename: str,
    _user: User = Depends(require_role("owner")),
) -> MemoryFile:
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = HERMES_HOME / "memories" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content = filepath.read_text(encoding="utf-8", errors="replace")
    return MemoryFile(name=filename, content=content[:50000], size=filepath.stat().st_size)


class HeartbeatInfo(BaseModel):
    content: str
    skills: list[str]
    agents_md: str
    dream_configured: bool = False
    dream_interval_h: Optional[float] = None
    history_entries: int = 0
    dream_cursor: int = 0
    memory_md_last_modified: Optional[str] = None


@router.get("/status/heartbeat", response_model=HeartbeatInfo)
async def get_heartbeat(
    _user: User = Depends(require_role("owner")),
) -> HeartbeatInfo:
    """Status der Hermes-Runtime: SOUL/Identitaet, Skills, Memory-Stand."""
    heartbeat = ""
    heartbeat_path = HERMES_HOME / "memories" / "USER.md"
    if heartbeat_path.exists():
        heartbeat = heartbeat_path.read_text(encoding="utf-8", errors="replace")

    skills = []
    skills_dir = HERMES_HOME / "skills"
    if skills_dir.exists():
        skills = [f.stem for f in skills_dir.iterdir() if f.is_file() and f.suffix == ".md"]

    agents_md = ""
    soul_path = HERMES_HOME / "SOUL.md"
    if soul_path.exists():
        agents_md = soul_path.read_text(encoding="utf-8", errors="replace")

    # Hermes nutzt always-on Memory statt eines Dream-Zyklus.
    dream_configured = False
    dream_interval_h: Optional[float] = None

    history_entries = 0
    memories_dir = HERMES_HOME / "memories"
    if memories_dir.exists():
        for hist in memories_dir.glob("history*.jsonl"):
            try:
                history_entries += sum(1 for _ in hist.open(encoding="utf-8"))
            except OSError:
                pass

    dream_cursor = 0

    memory_md_last_modified: Optional[str] = None
    memory_path = HERMES_HOME / "memories" / "MEMORY.md"
    if memory_path.exists():
        try:
            mtime = memory_path.stat().st_mtime
            memory_md_last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass

    return HeartbeatInfo(
        content=heartbeat,
        skills=sorted(skills),
        agents_md=agents_md,
        dream_configured=dream_configured,
        dream_interval_h=dream_interval_h,
        history_entries=history_entries,
        dream_cursor=dream_cursor,
        memory_md_last_modified=memory_md_last_modified,
    )
