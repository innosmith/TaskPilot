"""Intelligence-Router: Hermes Agent Brain, Sender-Profile, Skills, Triage-Statistiken.

Liefert aggregierte Einblicke in das Systemwissen von TaskPilot und dem
Hermes Agent, damit der Benutzer sieht, was der Agent gelernt hat.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import EmailTriage, User

logger = logging.getLogger("taskpilot.intelligence")

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

HERMES_HOME = Path(os.environ.get("TP_HERMES_HOME", os.path.expanduser("~/.hermes")))


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
    _user: User = Depends(get_current_user),
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
    _user: User = Depends(get_current_user),
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
    _user: User = Depends(get_current_user),
) -> AgentSkillsResponse:
    """Listet die verfügbaren Hermes-Skills mit Kurzbeschreibung."""
    skills_dir = HERMES_HOME / "skills"

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


# ── Agent Brain (Hermes) ─────────────────────────────────

class HermesBrainFile(BaseModel):
    name: str
    category: str
    content: str
    size: int
    last_modified: str | None = None


class HermesBrainResponse(BaseModel):
    files: list[HermesBrainFile]
    config_summary: dict
    honcho_status: str
    agent_model: str
    mcp_servers: list[str]


@router.get("/brain", response_model=HermesBrainResponse)
async def get_agent_brain(
    _user: User = Depends(get_current_user),
) -> HermesBrainResponse:
    """Vollständiger Einblick ins Hermes-Agent-Gehirn: Memory, User-Profil, Skills, Config."""
    import yaml

    files: list[HermesBrainFile] = []

    memories_dir = HERMES_HOME / "memories"
    if memories_dir.exists():
        for f in sorted(memories_dir.iterdir()):
            if f.is_file() and f.suffix in (".md", ".jsonl", ".txt"):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat()
                    files.append(HermesBrainFile(
                        name=f.name,
                        category="memory",
                        content=content[:50000],
                        size=f.stat().st_size,
                        last_modified=mtime,
                    ))
                except OSError:
                    continue

    for root_file in ("USER.md", "MEMORY.md", "AGENTS.md", "HEARTBEAT.md", "SOUL.md"):
        fp = HERMES_HOME / root_file
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).isoformat()
                files.append(HermesBrainFile(
                    name=root_file,
                    category="profile",
                    content=content[:50000],
                    size=fp.stat().st_size,
                    last_modified=mtime,
                ))
            except OSError:
                continue

    skills_dir = HERMES_HOME / "skills"
    if skills_dir.exists():
        for f in sorted(skills_dir.iterdir()):
            if f.is_file() and f.suffix == ".md":
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat()
                    files.append(HermesBrainFile(
                        name=f.name,
                        category="skill",
                        content=content[:50000],
                        size=f.stat().st_size,
                        last_modified=mtime,
                    ))
                except OSError:
                    continue

    config_summary = {}
    agent_model = "unbekannt"
    mcp_servers: list[str] = []

    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            agent_model = cfg.get("model", "unbekannt")
            config_summary = {
                "model": agent_model,
                "base_url": cfg.get("base_url", ""),
                "max_iterations": cfg.get("max_iterations", 0),
                "memory_enabled": cfg.get("memory", {}).get("memory_enabled", False),
                "memory_provider": cfg.get("memory", {}).get("provider", "local"),
                "approvals_mode": cfg.get("approvals", {}).get("mode", ""),
            }
            mcp_servers = list(cfg.get("mcp_servers", {}).keys())
        except (yaml.YAMLError, OSError):
            pass

    honcho_status = "nicht konfiguriert"
    honcho_path = HERMES_HOME / "honcho.json"
    if honcho_path.exists():
        try:
            import json
            honcho_cfg = json.loads(honcho_path.read_text(encoding="utf-8"))
            base_url = honcho_cfg.get("baseUrl", "")
            hosts = honcho_cfg.get("hosts", {})
            enabled_hosts = [k for k, v in hosts.items() if v.get("enabled")]
            honcho_status = f"aktiv ({base_url}, {len(enabled_hosts)} Host{'s' if len(enabled_hosts) != 1 else ''})"
        except (OSError, Exception):
            honcho_status = "Fehler beim Lesen"

    return HermesBrainResponse(
        files=files,
        config_summary=config_summary,
        honcho_status=honcho_status,
        agent_model=agent_model,
        mcp_servers=mcp_servers,
    )
