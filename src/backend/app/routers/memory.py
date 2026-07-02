import hashlib
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_role
from app.models import User
from app.services.hermes_config import get_hermes_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])

# Hermes-Home: memories/, skills/, SOUL.md, config.yaml
HERMES_HOME = get_hermes_home()

# Nur diese Memory-Dateien duerfen ueber die UI bearbeitet werden. history*.jsonl
# bleibt bewusst aussen vor (append-only Protokoll, kein manuelles Editieren).
EDITABLE_MEMORY_FILES = {"MEMORY.md", "USER.md"}
MAX_MEMORY_CHARS = 200_000


def _file_hash(text: str) -> str:
    """Stabiler Hash ueber den vollstaendigen Dateiinhalt (Optimistic Locking)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _backup_memory(path: Path) -> str:
    """Sicherheitsnetz vor dem Ueberschreiben: timestamped ``.bak`` + best-effort Git-Commit.

    Memory-Dateien sind via Bind-Mount sofort produktiv -- darum IMMER sichern. Die
    ``.bak``-Kopie ist garantiert; ist ``~/.hermes`` ein Git-Repo, wird zusaetzlich
    ein Commit versucht (best-effort, blockiert nie).
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + f".{ts}.bak")
    shutil.copy2(path, bak)
    home = get_hermes_home()
    if (home / ".git").exists():
        try:
            subprocess.run(
                ["git", "-C", str(home), "add", "-A"],
                check=False, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "-C", str(home), "commit", "-m", f"Memory-Backup {path.name} {ts}"],
                check=False, capture_output=True, timeout=10,
            )
        except Exception:  # noqa: BLE001 - Git ist nur Bonus, .bak ist die Garantie
            logger.warning("Git-Backup fuer Memory-Edit fehlgeschlagen (Kopie .bak existiert)")
    return bak.name


class MemoryFile(BaseModel):
    name: str
    content: str
    size: int
    editable: bool = False
    truncated: bool = False
    hash: str | None = None


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
                files.append(MemoryFile(
                    name=f.name,
                    content=content[:50000],
                    size=f.stat().st_size,
                    editable=f.name in EDITABLE_MEMORY_FILES,
                    truncated=len(content) > 50000,
                ))
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

    full = filepath.read_text(encoding="utf-8", errors="replace")
    truncated = len(full) > MAX_MEMORY_CHARS
    return MemoryFile(
        name=filename,
        content=full[:MAX_MEMORY_CHARS],
        size=filepath.stat().st_size,
        editable=filename in EDITABLE_MEMORY_FILES,
        truncated=truncated,
        # Hash ueber den vollstaendigen Inhalt -- Basis fuer Optimistic Locking.
        hash=_file_hash(full),
    )


class MemoryUpdate(BaseModel):
    content: str
    # Hash der beim Laden gesehenen Version -- schuetzt vor Lost Updates.
    base_hash: str | None = None


class MemoryUpdateResponse(BaseModel):
    name: str
    size: int
    hash: str
    backup: str


@router.put("/{filename}", response_model=MemoryUpdateResponse)
async def update_memory_file(
    filename: str,
    payload: MemoryUpdate,
    _user: User = Depends(require_role("owner")),
) -> MemoryUpdateResponse:
    """Speichert eine bearbeitbare Memory-Datei (mit Backup + Optimistic Lock).

    Nur ``MEMORY.md``/``USER.md``. Hat der Agent zwischenzeitlich geschrieben
    (Hash weicht ab), wird mit 409 abgelehnt -- der Berater laedt dann neu und
    entscheidet bewusst, statt eine Agenten-Aenderung lautlos zu ueberschreiben.
    """
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if filename not in EDITABLE_MEMORY_FILES:
        raise HTTPException(status_code=403, detail="Diese Memory-Datei ist nicht bearbeitbar.")
    if len(payload.content) > MAX_MEMORY_CHARS:
        raise HTTPException(status_code=413, detail=f"Inhalt zu gross (max. {MAX_MEMORY_CHARS} Zeichen).")

    filepath = HERMES_HOME / "memories" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    current = filepath.read_text(encoding="utf-8", errors="replace")
    if payload.base_hash is not None and _file_hash(current) != payload.base_hash:
        raise HTTPException(
            status_code=409,
            detail="Memory wurde zwischenzeitlich vom Agenten geaendert. Bitte neu laden.",
        )

    backup = _backup_memory(filepath)
    filepath.write_text(payload.content, encoding="utf-8")
    logger.info("Memory '%s' bearbeitet (Backup: %s)", filename, backup)
    return MemoryUpdateResponse(
        name=filename,
        size=len(payload.content.encode("utf-8")),
        hash=_file_hash(payload.content),
        backup=backup,
    )


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

    from app.services.hermes_config import discover_skills

    skills = [s["name"] for s in discover_skills()]

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
