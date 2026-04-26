"""Nanobot SDK Worker: Verarbeitet queued AgentJobs direkt via Python SDK.

Laeuft als Hintergrund-Task beim Backend-Start. Pollt alle 10 Sekunden nach
queued AgentJobs und verarbeitet sie sequentiell mit dem Nanobot SDK:

    bot = Nanobot.from_config()
    result = await bot.run(prompt, session_key=f"triage:{job_id}:{ts}")

Nanobot nutzt dabei seine konfigurierten MCP-Tools (email, taskpilot) um
E-Mails zu lesen, zu klassifizieren und Aktionen auszufuehren.
Jeder Durchlauf verwendet einen einzigartigen Session-Key (mit Timestamp),
damit keine alte Konversationshistorie wiederverwendet wird.

Nach der LLM-Klassifikation fuehrt der Worker deterministische Post-Processing-
Logik aus: JSON-Output parsen, Tasks erstellen, Drafts zuordnen.
"""

import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

from nanobot import Nanobot
from sqlalchemy import select, update

from app.database import async_session
from app.models import AgentJob, BoardColumn, EmailTriage, Project, Task

logger = logging.getLogger("taskpilot.nanobot_worker")

_worker_task: asyncio.Task | None = None
_bot: Nanobot | None = None

POLL_INTERVAL = 10
NANOBOT_CONFIG = Path.home() / ".nanobot" / "config.json"
TRIAGE_SKILL = Path.home() / ".nanobot" / "workspace" / "skills" / "mail-triage.md"

PIPELINE_COLUMNS = {
    "focus": "a0000000-0000-0000-0000-000000000001",
    "this_week": "a0000000-0000-0000-0000-000000000002",
    "next_week": "a0000000-0000-0000-0000-000000000003",
    "this_month": "a0000000-0000-0000-0000-000000000005",
}


def _load_triage_skill() -> str:
    """Liest den mail-triage.md Skill als Systeminstruktion."""
    if TRIAGE_SKILL.exists():
        return TRIAGE_SKILL.read_text(encoding="utf-8")
    logger.warning("Triage-Skill nicht gefunden: %s", TRIAGE_SKILL)
    return ""


async def _load_projects_context() -> str:
    """Laedt alle aktiven Projekte aus der DB und formatiert sie als Prompt-Kontext."""
    async with async_session() as db:
        result = await db.execute(
            select(Project)
            .where(Project.status != "archived")
            .order_by(Project.name)
        )
        projects = list(result.scalars().all())

    if not projects:
        return "## VERFUEGBARE PROJEKTE\nKeine aktiven Projekte vorhanden."

    lines = ["## VERFUEGBARE PROJEKTE", ""]
    for p in projects:
        lines.append(f'- "{p.name}" (id: {p.id})')
    lines.append("")
    lines.append("Waehle bei board_task das passendste Projekt aus dieser Liste fuer das Feld suggested_project.")
    lines.append("Falls kein Projekt passt, setze suggested_project auf null.")
    return "\n".join(lines)


async def _build_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt fuer einen email_triage Job aus Metadata.

    Laedt den Triage-Skill und die Projektliste bei jedem Aufruf frisch,
    damit Aenderungen sofort wirksam werden.
    """
    skill_text = _load_triage_skill()
    projects_context = await _load_projects_context()

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

{projects_context}

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
6. Erstelle Draft falls quick_response (bei board_task uebernimmt das Backend die Task-Erstellung automatisch)
7. Gib den PFLICHT-JSON-Block aus (Schritt 8 im Skill)
8. Melde das Ergebnis mit update_agent_job("{job.id}", status="completed"|"awaiting_approval", output="...")
"""


def _extract_json_block(content: str) -> dict | None:
    """Extrahiert den JSON-Block aus dem LLM-Output."""
    pattern = r"```json\s*\n(.*?)\n\s*```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("JSON-Block gefunden aber nicht parsebar: %s", match.group(1)[:200])
            return None

    # Fallback: letztes {...} im Text
    json_pattern = r"\{[^{}]*\"label\"[^{}]*\"triage_class\"[^{}]*\}"
    matches = list(re.finditer(json_pattern, content, re.DOTALL))
    if matches:
        try:
            return json.loads(matches[-1].group(0))
        except json.JSONDecodeError:
            return None

    return None


def _match_project(suggested_name: str | None, projects: list) -> tuple | None:
    """Matched einen Projektnamen gegen die DB-Projekte (case-insensitive contains)."""
    if not suggested_name or not projects:
        return None
    name_lower = suggested_name.lower()
    for p in projects:
        if name_lower in p.name.lower() or p.name.lower() in name_lower:
            return p
    return None


def _determine_pipeline_column(deadline_str: str | None) -> str | None:
    """Bestimmt die Pipeline-Spalte basierend auf der Deadline."""
    if not deadline_str:
        return PIPELINE_COLUMNS["this_week"]
    try:
        deadline = date.fromisoformat(deadline_str)
    except ValueError:
        return PIPELINE_COLUMNS["this_week"]

    today = date.today()
    delta = (deadline - today).days

    if delta <= 1:
        return PIPELINE_COLUMNS["focus"]
    if delta <= 7:
        return PIPELINE_COLUMNS["this_week"]
    if delta <= 14:
        return PIPELINE_COLUMNS["next_week"]
    if delta <= 31:
        return PIPELINE_COLUMNS["this_month"]
    return PIPELINE_COLUMNS["this_month"]


async def _post_process_triage(job_id, content: str, meta: dict) -> str:
    """Deterministische Post-Processing-Logik nach LLM-Klassifikation.

    Parst den JSON-Block, erstellt Tasks bei board_task, speichert draft_id
    bei quick_response, und aktualisiert den EmailTriage-Record.

    Returns: finaler Status fuer den AgentJob.
    """
    parsed = _extract_json_block(content)
    if parsed is None:
        logger.warning("Job %s: Kein JSON-Block im Output gefunden", job_id)
        return "completed"

    triage_class = parsed.get("triage_class")
    label = parsed.get("label")
    draft_id = parsed.get("draft_id")
    deadline = parsed.get("deadline")
    task_title = parsed.get("task_title")
    task_description = parsed.get("task_description")
    suggested_project = parsed.get("suggested_project")
    rationale = parsed.get("rationale")

    logger.info(
        "Job %s: JSON parsed -- label=%s, triage_class=%s, draft_id=%s",
        job_id, label, triage_class, draft_id,
    )

    async with async_session() as db:
        # EmailTriage aktualisieren
        await db.execute(
            update(EmailTriage)
            .where(EmailTriage.agent_job_id == job_id)
            .values(
                triage_class=triage_class,
                suggested_action={
                    "label": label,
                    "triage_class": triage_class,
                    "deadline": deadline,
                    "task_title": task_title,
                    "suggested_project": suggested_project,
                    "draft_id": draft_id,
                    "rationale": rationale,
                },
                status="acted" if triage_class != "quick_response" else "processing",
            )
        )

        final_status = "completed"

        if triage_class == "board_task" and task_title:
            # Projekte laden und matchen
            proj_result = await db.execute(
                select(Project).where(Project.status != "archived").order_by(Project.name)
            )
            projects = list(proj_result.scalars().all())
            matched_project = _match_project(suggested_project, projects)
            if not matched_project and projects:
                matched_project = projects[0]

            if matched_project:
                # Erste Board-Spalte des Projekts laden
                col_result = await db.execute(
                    select(BoardColumn)
                    .where(BoardColumn.project_id == matched_project.id)
                    .order_by(BoardColumn.position)
                    .limit(1)
                )
                first_col = col_result.scalar_one_or_none()

                if first_col:
                    pipeline_col_id = _determine_pipeline_column(deadline)
                    email_message_id = meta.get("email_message_id")

                    due_date = None
                    if deadline:
                        try:
                            due_date = date.fromisoformat(deadline)
                        except ValueError:
                            pass

                    max_pos_result = await db.execute(
                        select(Task.board_position)
                        .where(Task.board_column_id == first_col.id)
                        .order_by(Task.board_position.desc())
                        .limit(1)
                    )
                    max_pos_row = max_pos_result.scalar_one_or_none()
                    next_pos = (max_pos_row or 0) + 1

                    new_task = Task(
                        title=task_title,
                        description=task_description or f"Erstellt aus E-Mail: {meta.get('subject', '')}",
                        project_id=matched_project.id,
                        board_column_id=first_col.id,
                        board_position=next_pos,
                        pipeline_column_id=pipeline_col_id,
                        email_message_id=email_message_id,
                        due_date=due_date,
                        needs_review=True,
                        assignee="me",
                    )
                    db.add(new_task)
                    logger.info(
                        "Job %s: Task erstellt '%s' in Projekt '%s' (needs_review=True)",
                        job_id, task_title, matched_project.name,
                    )

        elif triage_class == "quick_response" and draft_id:
            # draft_id in AgentJob-Metadata speichern
            job_result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                existing_meta = dict(job.metadata_json or {})
                existing_meta["draft_id"] = draft_id
                job.metadata_json = existing_meta
            final_status = "awaiting_approval"

        await db.commit()

    return final_status


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


async def _process_job(bot: Nanobot, job_id, job_type: str, prompt: str, meta: dict) -> None:
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

        if job_type == "email_triage":
            status = await _post_process_triage(job_id, content, meta)
        else:
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
                meta = job.metadata_json or {}
                if job.job_type == "email_triage":
                    prompt = await _build_triage_prompt(job)
                else:
                    prompt = f"Fuehre den AgentJob {job.id} aus: {job.metadata_json}"

                await _process_job(bot, job.id, job.job_type or "generic", prompt, meta)
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
