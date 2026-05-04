import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/memory", tags=["memory"])

HERMES_HOME = Path(os.environ.get("TP_HERMES_HOME", os.path.expanduser("~/.hermes")))


class MemoryFile(BaseModel):
    name: str
    content: str
    size: int


@router.get("", response_model=list[MemoryFile])
async def list_memory_files(
    _user: User = Depends(get_current_user),
) -> list[MemoryFile]:
    memory_dir = HERMES_HOME / "memories"
    if not memory_dir.exists():
        memory_dir.mkdir(parents=True, exist_ok=True)
        return []

    files = []
    for f in sorted(memory_dir.iterdir()):
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
    _user: User = Depends(get_current_user),
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
    _user: User = Depends(get_current_user),
) -> HeartbeatInfo:
    import yaml

    heartbeat = ""
    heartbeat_path = HERMES_HOME / "HEARTBEAT.md"
    if heartbeat_path.exists():
        heartbeat = heartbeat_path.read_text(encoding="utf-8", errors="replace")

    skills = []
    skills_dir = HERMES_HOME / "skills"
    if skills_dir.exists():
        skills = [f.stem for f in skills_dir.iterdir() if f.is_file() and f.suffix == ".md"]

    agents_md = ""
    agents_path = HERMES_HOME / "AGENTS.md"
    if agents_path.exists():
        agents_md = agents_path.read_text(encoding="utf-8", errors="replace")

    dream_configured = False
    dream_interval_h: Optional[float] = None
    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            memory_cfg = cfg.get("memory", {})
            if memory_cfg.get("memory_enabled"):
                dream_configured = True
        except (yaml.YAMLError, OSError):
            pass

    history_entries = 0
    history_path = HERMES_HOME / "memories" / "history.jsonl"
    if history_path.exists():
        try:
            history_entries = sum(1 for _ in history_path.open(encoding="utf-8"))
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
