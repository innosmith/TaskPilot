"""Intelligence-Router: Sender-Profile, Agent-Skills, Triage-Statistiken.

Liefert aggregierte Einblicke in das Systemwissen von TaskPilot,
damit der Benutzer sieht, was der Agent gelernt hat.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_role
from app.database import get_db
from app.models import EmailTriage, User

logger = logging.getLogger("taskpilot.intelligence")

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


# ── Sender-Profile ───────────────────────────────────────

class SenderProfile(BaseModel):
    email: str
    name: str | None = None
    total_emails: int
    auto_reply_count: int
    task_count: int
    fyi_count: int
    reply_rate: float
    last_seen: str | None = None


class SenderProfilesResponse(BaseModel):
    profiles: list[SenderProfile]
    total_senders: int


@router.get("/sender-profiles", response_model=SenderProfilesResponse)
async def get_sender_profiles(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("owner")),
) -> SenderProfilesResponse:
    """Top-Absender mit Triage-Verteilung."""
    query = (
        select(
            EmailTriage.sender_email,
            EmailTriage.sender_name,
            func.count().label("total"),
            func.count().filter(EmailTriage.triage_class == "auto_reply").label("auto_reply"),
            func.count().filter(EmailTriage.triage_class == "task").label("task"),
            func.count().filter(EmailTriage.triage_class == "fyi").label("fyi"),
            func.count().filter(EmailTriage.reply_expected.is_(True)).label("reply_expected"),
            func.max(EmailTriage.created_at).label("last_seen"),
        )
        .where(EmailTriage.sender_email.isnot(None))
        .group_by(EmailTriage.sender_email, EmailTriage.sender_name)
        .order_by(func.count().desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    profiles = []
    for row in rows:
        total = row.total or 1
        reply_count = (row.auto_reply or 0) + (row.reply_expected or 0)
        profiles.append(SenderProfile(
            email=row.sender_email or "",
            name=row.sender_name,
            total_emails=total,
            auto_reply_count=row.auto_reply or 0,
            task_count=row.task or 0,
            fyi_count=row.fyi or 0,
            reply_rate=round(reply_count / total, 2) if total > 0 else 0.0,
            last_seen=row.last_seen.isoformat() if row.last_seen else None,
        ))

    total_q = await db.execute(
        select(func.count(func.distinct(EmailTriage.sender_email)))
        .where(EmailTriage.sender_email.isnot(None))
    )
    total_senders = total_q.scalar_one_or_none() or 0

    return SenderProfilesResponse(profiles=profiles, total_senders=total_senders)


# ── Triage-Statistiken ──────────────────────────────────

class TriageStats(BaseModel):
    total: int
    auto_reply: int
    task: int
    fyi: int
    reply_expected_count: int
    avg_per_day: float
    period_days: int


@router.get("/triage-stats", response_model=TriageStats)
async def get_triage_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("owner")),
) -> TriageStats:
    """Triage-Statistiken der letzten N Tage."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(
        func.count().label("total"),
        func.count().filter(EmailTriage.triage_class == "auto_reply").label("auto_reply"),
        func.count().filter(EmailTriage.triage_class == "task").label("task"),
        func.count().filter(EmailTriage.triage_class == "fyi").label("fyi"),
        func.count().filter(EmailTriage.reply_expected.is_(True)).label("reply_expected"),
    ).where(EmailTriage.created_at >= cutoff)

    result = await db.execute(query)
    row = result.one()

    total = row.total or 0
    avg = round(total / max(days, 1), 1)

    return TriageStats(
        total=total,
        auto_reply=row.auto_reply or 0,
        task=row.task or 0,
        fyi=row.fyi or 0,
        reply_expected_count=row.reply_expected or 0,
        avg_per_day=avg,
        period_days=days,
    )


# ── Agent-Skills ─────────────────────────────────────────

class AgentSkill(BaseModel):
    name: str
    description: str
    content: str = ""


class AgentSkillsResponse(BaseModel):
    skills: list[AgentSkill]


@router.get("/skills", response_model=AgentSkillsResponse)
async def get_agent_skills(
    _user: User = Depends(require_role("owner")),
) -> AgentSkillsResponse:
    """Listet die verfügbaren Hermes-Skills mit Kurzbeschreibung."""
    from app.services.hermes_config import get_hermes_home

    skills_dir = get_hermes_home() / "skills"

    skills: list[AgentSkill] = []
    if skills_dir.exists():
        for f in sorted(skills_dir.iterdir()):
            if f.is_file() and f.suffix == ".md":
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    first_line = ""
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            first_line = stripped[:200]
                            break
                    skills.append(AgentSkill(name=f.stem, description=first_line, content=content))
                except OSError:
                    continue

    return AgentSkillsResponse(skills=skills)


# ── Hermes-Brain (zentraler Runtime-Status) ──────────────

class BrainFile(BaseModel):
    name: str
    content: str
    size: int
    last_modified: str | None = None


class BrainStatus(BaseModel):
    runtime: str = "hermes"
    model: str | None = None
    mcp_servers: list[str] = []
    skills: list[str] = []
    user_profile: BrainFile | None = None
    memory: BrainFile | None = None
    soul: BrainFile | None = None


def _read_brain_file(path) -> BrainFile | None:
    from datetime import datetime, timezone as _tz

    if not path.exists() or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        stat = path.stat()
        return BrainFile(
            name=path.name,
            content=content[:50000],
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=_tz.utc).isoformat(),
        )
    except OSError:
        return None


@router.get("/brain", response_model=BrainStatus)
async def get_brain(
    _user: User = Depends(require_role("owner")),
) -> BrainStatus:
    """Aggregierter Hermes-Status: Modell, MCP-Server, Skills, Memory, Identität.

    Single Source of Truth für den Intelligence-Tab im Frontend.
    """
    import yaml
    from app.services.hermes_config import get_hermes_home

    home = get_hermes_home()
    config_path = home / "config.yaml"

    model: str | None = None
    mcp_servers: list[str] = []
    if config_path.exists():
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            model = (cfg.get("model") or {}).get("default")
            mcp_servers = sorted((cfg.get("mcp_servers") or {}).keys())
        except Exception:
            pass

    skills: list[str] = []
    skills_dir = home / "skills"
    if skills_dir.exists():
        skills = sorted(f.stem for f in skills_dir.iterdir() if f.is_file() and f.suffix == ".md")

    return BrainStatus(
        runtime="hermes",
        model=model,
        mcp_servers=mcp_servers,
        skills=skills,
        user_profile=_read_brain_file(home / "memories" / "USER.md"),
        memory=_read_brain_file(home / "memories" / "MEMORY.md"),
        soul=_read_brain_file(home / "SOUL.md"),
    )
