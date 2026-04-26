"""Nanobot SDK Worker: Verarbeitet queued AgentJobs direkt via Python SDK.

Laeuft als Hintergrund-Task beim Backend-Start. Pollt alle 10 Sekunden nach
queued AgentJobs und verarbeitet sie sequentiell mit dem Nanobot SDK:

    bot = Nanobot.from_config()
    result = await bot.run(prompt, session_key=f"triage:{job_id}:{ts}")

Nanobot nutzt dabei seine konfigurierten MCP-Tools (email, taskpilot) um
E-Mails zu lesen, zu klassifizieren und Aktionen auszufuehren.
Jeder Durchlauf verwendet einen einzigartigen Session-Key (mit Timestamp),
damit keine alte Konversationshistorie wiederverwendet wird.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from nanobot import Nanobot
from sqlalchemy import select, update

from app.database import async_session
from app.models import AgentJob, EmailTriage

logger = logging.getLogger("taskpilot.nanobot_worker")

_worker_task: asyncio.Task | None = None
_bot: Nanobot | None = None

POLL_INTERVAL = 10
NANOBOT_CONFIG = Path.home() / ".nanobot" / "config.json"
TRIAGE_SKILL = Path.home() / ".nanobot" / "workspace" / "skills" / "mail-triage.md"


def _load_triage_skill() -> str:
    """Liest den mail-triage.md Skill als Systeminstruktion."""
    if TRIAGE_SKILL.exists():
        return TRIAGE_SKILL.read_text(encoding="utf-8")
    logger.warning("Triage-Skill nicht gefunden: %s", TRIAGE_SKILL)
    return ""


def _build_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt fuer einen email_triage Job aus Metadata.

    Laedt den Triage-Skill bei jedem Aufruf frisch, damit Aenderungen
    an mail-triage.md sofort wirksam werden.
    """
    skill_text = _load_triage_skill()

    meta = job.metadata_json or {}
    email_id = meta.get("email_message_id", "")
    subject = meta.get("subject", "")
    from_addr = meta.get("from_address", "")
    from_name = meta.get("from_name", "")
    preview = meta.get("body_preview", "")
    inference = meta.get("inference_classification", "")

    return f"""## TRIAGE-INSTRUKTIONEN (STRIKT befolgen!)

{skill_text}

---

## AKTUELLER JOB

Du hast einen email_triage Job erhalten. Fuehre den kompletten Triage-Ablauf gemaess den obigen Instruktionen durch.

**Job-ID:** {job.id}
**E-Mail Message-ID:** {email_id}
**Betreff:** {subject}
**Von:** {from_name} <{from_addr}>
**Microsoft Inference:** {inference}
**Body-Vorschau:** {preview[:300]}

WICHTIG: Befolge die Prioritaetsreihenfolge (Stufe 1 → Stufe 2 → Stufe 3) STRIKT.
- Pruefe ZUERST ob Stufe 1 (Signale) zutrifft.
- Pruefe DANN ob Stufe 2 (System) zutrifft.
- Nur wenn weder Stufe 1 noch 2 passen, wende Stufe 3 (Standardregeln) an.

Fuehre jetzt den Triage-Ablauf durch:
1. Lies die E-Mail mit get_email("{email_id}")
2. Lies die Kategorien mit get_email_categories("{email_id}")
3. Klassifiziere gemaess der Prioritaetsreihenfolge
4. Setze die Outlook-Kategorie
5. Verschiebe bei Bedarf (System/Newsletter/Junk/Kalender)
6. Erstelle Draft oder Task falls noetig
7. Melde das Ergebnis mit update_agent_job("{job.id}", status="completed"|"awaiting_approval", output="...")
"""


async def _init_bot() -> Nanobot | None:
    """Initialisiert den Nanobot einmalig."""
    global _bot
    if _bot is not None:
        return _bot
    if not NANOBOT_CONFIG.exists():
        logger.error("Nanobot-Config nicht gefunden: %s", NANOBOT_CONFIG)
        return None
    try:
        _bot = Nanobot.from_config(config_path=str(NANOBOT_CONFIG))
        logger.info("Nanobot SDK initialisiert (Config: %s)", NANOBOT_CONFIG)
        return _bot
    except Exception:
        logger.exception("Nanobot SDK Initialisierung fehlgeschlagen")
        return None


async def _process_job(bot: Nanobot, job_id, job_type: str, prompt: str) -> None:
    """Verarbeitet einen einzelnen AgentJob via Nanobot SDK."""
    session_key = f"{job_type}:{job_id}:{int(time.time())}"
    logger.info("Starte Job %s (type=%s, session=%s)", job_id, job_type, session_key)

    async with async_session() as db:
        await db.execute(
            update(AgentJob)
            .where(AgentJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    try:
        result = await bot.run(prompt, session_key=session_key)
        content = result.content or ""
        logger.info("Job %s abgeschlossen: %s", job_id, content[:200])

        status = "completed"
        if "awaiting_approval" in content.lower():
            status = "awaiting_approval"

        async with async_session() as db:
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status=status,
                    output=content[:4000],
                    completed_at=datetime.now(timezone.utc),
                )
            )
            if job_type == "email_triage":
                await db.execute(
                    update(EmailTriage)
                    .where(EmailTriage.agent_job_id == job_id)
                    .values(status="acted" if status == "completed" else "processing")
                )
            await db.commit()

    except Exception as e:
        logger.exception("Job %s fehlgeschlagen", job_id)
        async with async_session() as db:
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status="failed",
                    error_message=str(e)[:2000],
                    completed_at=datetime.now(timezone.utc),
                )
            )
            if job_type == "email_triage":
                await db.execute(
                    update(EmailTriage)
                    .where(EmailTriage.agent_job_id == job_id)
                    .values(status="dismissed")
                )
            await db.commit()


async def _worker_loop() -> None:
    """Pollt nach queued Jobs und verarbeitet sie sequentiell."""
    await asyncio.sleep(3)

    bot = await _init_bot()
    if bot is None:
        logger.error("Nanobot-Worker kann nicht starten (SDK nicht verfuegbar)")
        return

    logger.info("Nanobot-Worker gestartet -- pollt alle %ds nach queued Jobs", POLL_INTERVAL)

    while True:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(AgentJob)
                    .where(AgentJob.status == "queued")
                    .order_by(AgentJob.created_at)
                    .limit(1)
                )
                job = result.scalar_one_or_none()

            if job is not None:
                if job.job_type == "email_triage":
                    prompt = _build_triage_prompt(job)
                else:
                    prompt = f"Fuehre den AgentJob {job.id} aus: {job.metadata_json}"

                await _process_job(bot, job.id, job.job_type or "generic", prompt)
            else:
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Nanobot-Worker: unerwarteter Fehler")
            await asyncio.sleep(POLL_INTERVAL)


async def start_nanobot_worker() -> None:
    """Startet den Nanobot-Worker als Hintergrund-Task."""
    global _worker_task
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Nanobot-Worker: Hintergrund-Task gestartet")


async def stop_nanobot_worker() -> None:
    """Stoppt den Nanobot-Worker."""
    global _worker_task, _bot
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
    _bot = None
    logger.info("Nanobot-Worker gestoppt")
