import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/memory", tags=["memory"])

NANOBOT_WORKSPACE = Path(os.environ.get("TP_NANOBOT_WORKSPACE", os.path.expanduser("~/.nanobot/workspace")))


class MemoryFile(BaseModel):
    name: str
    content: str
    size: int


@router.get("", response_model=list[MemoryFile])
async def list_memory_files(
    _user: User = Depends(get_current_user),
) -> list[MemoryFile]:
    memory_dir = NANOBOT_WORKSPACE / "memory"
    if not memory_dir.exists():
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

    filepath = NANOBOT_WORKSPACE / "memory" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content = filepath.read_text(encoding="utf-8", errors="replace")
    return MemoryFile(name=filename, content=content[:50000], size=filepath.stat().st_size)


class HeartbeatInfo(BaseModel):
    content: str
    skills: list[str]
    agents_md: str


@router.get("/status/heartbeat", response_model=HeartbeatInfo)
async def get_heartbeat(
    _user: User = Depends(get_current_user),
) -> HeartbeatInfo:
    heartbeat = ""
    heartbeat_path = NANOBOT_WORKSPACE / "HEARTBEAT.md"
    if heartbeat_path.exists():
        heartbeat = heartbeat_path.read_text(encoding="utf-8", errors="replace")

    skills = []
    skills_dir = NANOBOT_WORKSPACE / "skills"
    if skills_dir.exists():
        skills = [f.stem for f in skills_dir.iterdir() if f.is_file() and f.suffix == ".md"]

    agents_md = ""
    agents_path = NANOBOT_WORKSPACE / "AGENTS.md"
    if agents_path.exists():
        agents_md = agents_path.read_text(encoding="utf-8", errors="replace")

    return HeartbeatInfo(content=heartbeat, skills=sorted(skills), agents_md=agents_md)
