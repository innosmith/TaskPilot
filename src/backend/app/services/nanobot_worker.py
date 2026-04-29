"""Nanobot SDK Worker: Verarbeitet queued AgentJobs direkt via Python SDK.

Läuft als Hintergrund-Task beim Backend-Start. Pollt alle 10 Sekunden nach
queued AgentJobs und verarbeitet sie sequentiell mit dem Nanobot SDK:

    bot = Nanobot.from_config()
    result = await bot.run(prompt, session_key=f"triage:{job_id}:{ts}")

Nanobot nutzt dabei seine konfigurierten MCP-Tools (email, taskpilot) um
E-Mails zu lesen, zu klassifizieren und Aktionen auszuführen.
Jeder Durchlauf verwendet einen einzigartigen Session-Key (mit Timestamp),
damit keine alte Konversationshistorie wiederverwendet wird.

Nach der LLM-Klassifikation führt der Worker deterministische Post-Processing-
Logik aus: JSON-Output parsen, Tasks erstellen, Drafts zuordnen.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from nanobot import Nanobot
from sqlalchemy import select, update

from app.database import async_session
from app.models import AgentJob, BoardColumn, EmailTriage, Project, Task

logger = logging.getLogger("taskpilot.nanobot_worker")

_worker_task: asyncio.Task | None = None
_bot: Nanobot | None = None

POLL_INTERVAL = 10
REAP_INTERVAL = 60
STALE_TIMEOUT_MINUTES = 30
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
    """Lädt alle aktiven Projekte aus der DB und formatiert sie als Prompt-Kontext."""
    async with async_session() as db:
        result = await db.execute(
            select(Project)
            .where(Project.status != "archived")
            .order_by(Project.name)
        )
        projects = list(result.scalars().all())

    if not projects:
        return "## VERFÜGBARE PROJEKTE\nKeine aktiven Projekte vorhanden."

    lines = ["## VERFÜGBARE PROJEKTE", ""]
    for p in projects:
        lines.append(f'- "{p.name}" (id: {p.id})')
    lines.append("")
    lines.append("Wähle bei triage_class='task' das passendste Projekt aus dieser Liste für das Feld suggested_project.")
    lines.append("Falls kein Projekt passt, setze suggested_project auf null.")
    return "\n".join(lines)


async def _build_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt für einen email_triage Job aus Metadata.

    Lädt den Triage-Skill und die Projektliste bei jedem Aufruf frisch,
    damit Änderungen sofort wirksam werden.
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
    conversation_id = meta.get("conversation_id", "")

    thread_hint = ""
    if conversation_id:
        thread_hint = f"""
**Konversations-ID:** {conversation_id}
→ Lade den Thread mit get_thread("{conversation_id}") für vollständigen Kontext.
→ Lade die Absender-History mit search_sender_history("{from_addr}") um Kommunikationsmuster zu erkennen.
"""

    return f"""## TRIAGE-INSTRUKTIONEN (STRIKT befolgen!)

{skill_text}

---

{projects_context}

---

## AKTUELLER JOB

Du hast einen email_triage Job erhalten. Führe den kompletten Triage-Ablauf gemäss den obigen Instruktionen durch.

**Job-ID:** {job.id}
**E-Mail Message-ID:** {email_id}
**Betreff:** {subject}
**Von:** {from_name} <{from_addr}>
**Microsoft Inference:** {inference}
**Body-Vorschau:** {preview[:300]}
{thread_hint}

## PFLICHT-AUFRUFE VOR JEDER KLASSIFIKATION UND DRAFT-ERSTELLUNG

Du MUSST die folgenden drei Kontext-Quellen laden, BEVOR du klassifizierst oder einen Draft erstellst:
1. **get_thread("{conversation_id or ''}")** -- Thread-Kontext laden (PFLICHT falls conversation_id vorhanden)
2. **search_sender_history("{from_addr}")** -- Absender-History laden (IMMER PFLICHT)
3. **get_sender_profile("{from_addr}")** -- Absender-Profil laden (IMMER PFLICHT)

Erstelle NIEMALS einen Draft ohne diese drei Kontext-Quellen geladen zu haben!

---

WICHTIG: Befolge die Prioritätsreihenfolge (Stufe 1 → Stufe 2 → Stufe 3) STRIKT.
- Prüfe ZUERST ob Stufe 1 (Signale) zutrifft.
- Prüfe DANN ob Stufe 2 (System) zutrifft.
- Nur wenn weder Stufe 1 noch 2 passen, wende Stufe 3 (Standardregeln) an.

Führe jetzt den Triage-Ablauf durch:
1. Lies die E-Mail mit get_email("{email_id}")
2. Lies die Kategorien mit get_email_categories("{email_id}")
3. Lade Thread-Kontext, Absender-History und Absender-Profil (PFLICHT!)
4. Klassifiziere gemäss der Prioritätsreihenfolge
5. Setze die Outlook-Kategorie
6. Verschiebe bei Bedarf (System/Newsletter/Junk/Kalender)
7. Erstelle Draft falls auto_reply (bei task übernimmt das Backend die Task-Erstellung automatisch)
8. Gib den PFLICHT-JSON-Block aus (Schritt 8 im Skill)
9. Aktualisiere das Absender-Profil (Schritt 9 im Skill)
10. Melde das Ergebnis mit update_agent_job("{job.id}", status="completed"|"awaiting_approval", output="...")
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

    Parst den JSON-Block, erstellt Tasks bei 'task', speichert draft_id
    bei 'auto_reply', und aktualisiert den EmailTriage-Record.
    Returns: finaler Status für den AgentJob.
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
    reply_expected = bool(parsed.get("reply_expected", False))

    # Legacy-Werte migrieren
    if triage_class == "quick_response":
        triage_class = "auto_reply"
    elif triage_class == "board_task":
        triage_class = "task"
        reply_expected = True
    elif triage_class == "bedenkzeit":
        triage_class = "task"

    logger.info(
        "Job %s: JSON parsed -- label=%s, triage_class=%s, reply_expected=%s, draft_id=%s",
        job_id, label, triage_class, reply_expected, draft_id,
    )

    async with async_session() as db:
        await db.execute(
            update(EmailTriage)
            .where(EmailTriage.agent_job_id == job_id)
            .values(
                triage_class=triage_class,
                reply_expected=reply_expected,
                suggested_action={
                    "label": label,
                    "triage_class": triage_class,
                    "reply_expected": reply_expected,
                    "deadline": deadline,
                    "task_title": task_title,
                    "suggested_project": suggested_project,
                    "draft_id": draft_id,
                    "rationale": rationale,
                },
                status="acted" if triage_class != "auto_reply" else "processing",
            )
        )

        final_status = "completed"

        if triage_class == "task" and task_title:
            proj_result = await db.execute(
                select(Project).where(Project.status != "archived").order_by(Project.name)
            )
            projects = list(proj_result.scalars().all())
            matched_project = _match_project(suggested_project, projects)
            if not matched_project and projects:
                matched_project = projects[0]

            if matched_project:
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
                        "Job %s: Task erstellt '%s' in Projekt '%s' (reply_expected=%s)",
                        job_id, task_title, matched_project.name, reply_expected,
                    )

        elif triage_class == "auto_reply" and draft_id:
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
    """Initialisiert den Nanobot einmalig.

    Liest fehlende Env-Vars (z.B. Pipedrive-Token) aus der DB (User-Settings),
    damit die Nanobot-Config ${VAR}-Platzhalter auflösen kann.
    DB ist Single Source of Truth -- .env.dev dient nur als Fallback.
    """
    global _bot
    if _bot is not None:
        return _bot
    if not NANOBOT_CONFIG.exists():
        logger.error("Nanobot-Config nicht gefunden: %s", NANOBOT_CONFIG)
        return None

    await _populate_env_from_db()

    try:
        _bot = Nanobot.from_config(config_path=str(NANOBOT_CONFIG))
        logger.info("Nanobot SDK initialisiert (Config: %s)", NANOBOT_CONFIG)
        return _bot
    except Exception:
        logger.exception("Nanobot SDK Initialisierung fehlgeschlagen")
        return None


async def _populate_env_from_db() -> None:
    """Liest API-Tokens aus den User-Settings (Owner) und setzt sie als Env-Vars,
    falls sie noch nicht gesetzt sind. So bleibt die DB die einzige Quelle."""
    _ENV_KEYS = {
        "pipedrive_api_token": "TP_PIPEDRIVE_API_TOKEN",
        "pipedrive_domain": "TP_PIPEDRIVE_DOMAIN",
        "toggl_api_token": "TP_TOGGL_API_TOKEN",
        "toggl_workspace_id": "TP_TOGGL_WORKSPACE_ID",
        "bexio_api_token": "TP_BEXIO_API_TOKEN",
    }
    try:
        async with async_session() as db:
            from app.models import User
            result = await db.execute(
                select(User.settings).where(User.role == "owner").limit(1)
            )
            settings = result.scalar_one_or_none() or {}

        for db_key, env_key in _ENV_KEYS.items():
            if not os.environ.get(env_key):
                value = settings.get(db_key, "")
                if value:
                    os.environ[env_key] = str(value)
                    logger.info("Env-Var %s aus DB-Settings gesetzt", env_key)
                else:
                    os.environ[env_key] = ""
                    logger.debug("Env-Var %s auf leer gesetzt (kein DB-Wert)", env_key)

        # SIGNA-Env-Vars: TP_ISI_* wird von Pydantic geladen, MCP braucht sie auch
        for key in ("TP_ISI_HOST", "TP_ISI_DB", "TP_ISI_USER", "TP_ISI_SECRET"):
            if not os.environ.get(key):
                os.environ[key] = ""
                logger.debug("Env-Var %s auf leer gesetzt (nicht in Umgebung)", key)
    except Exception:
        logger.warning("DB-Settings konnten nicht gelesen werden -- Env-Vars bleiben wie sie sind")


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


async def _reap_stale_jobs() -> int:
    """Setzt running-Jobs, die länger als STALE_TIMEOUT_MINUTES laufen, auf failed."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT_MINUTES)
    async with async_session() as db:
        result = await db.execute(
            update(AgentJob)
            .where(
                AgentJob.status == "running",
                AgentJob.started_at < cutoff,
            )
            .values(
                status="failed",
                error_message=f"Timeout: Job lief über {STALE_TIMEOUT_MINUTES} Minuten ohne Abschluss",
                completed_at=datetime.now(timezone.utc),
            )
            .returning(AgentJob.id)
        )
        reaped_ids = result.scalars().all()
        if reaped_ids:
            logger.warning(
                "Reaper: %d stale running-Jobs auf failed gesetzt: %s",
                len(reaped_ids),
                [str(i) for i in reaped_ids],
            )
        await db.commit()
    return len(reaped_ids)


async def _worker_loop() -> None:
    """Pollt nach queued Jobs und verarbeitet sie sequentiell."""
    await asyncio.sleep(3)

    bot = await _init_bot()
    if bot is None:
        logger.error("Nanobot-Worker kann nicht starten (SDK nicht verfügbar)")
        return

    logger.info("Nanobot-Worker gestartet -- pollt alle %ds nach queued Jobs", POLL_INTERVAL)

    last_reap = time.monotonic()

    while True:
        try:
            # Reaper periodisch ausführen
            if time.monotonic() - last_reap >= REAP_INTERVAL:
                await _reap_stale_jobs()
                last_reap = time.monotonic()

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
                    prompt = f"Führe den AgentJob {job.id} aus: {job.metadata_json}"

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
