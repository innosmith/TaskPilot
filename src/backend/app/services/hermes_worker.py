"""Hermes Agent Worker: Verarbeitet queued AgentJobs via persistentem AIAgent.

Läuft als Hintergrund-Task beim Backend-Start
oder als eigenständiger Docker-Container.

Kern-Architektur:
- Ein persistenter AIAgent pro Worker-Prozess (MCP-Connections bleiben offen)
- Model-Switch pro Job via agent.model = job.llm_model
- PG NOTIFY für Chat-Jobs (sofortige Reaktion)
- Polling für reguläre Jobs (10s Intervall)
- Stream-Callback für Chat-Streaming via PG NOTIFY
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from sqlalchemy import select, update

from app.database import async_session
from app.models import AgentJob, BoardColumn, EmailTriage, Project, Task, User

logger = logging.getLogger("taskpilot.hermes_worker")

_worker_task: asyncio.Task | None = None
_listener_task: asyncio.Task | None = None
_agent = None
_agent_lock = asyncio.Lock()

POLL_INTERVAL = 10
REAP_INTERVAL = 60
DRAFT_CLEANUP_INTERVAL = 300
STALE_TIMEOUT_MINUTES = 30

HERMES_HOME = Path(os.environ.get("TP_HERMES_HOME", os.path.expanduser("~/.hermes")))
TRIAGE_SKILL = HERMES_HOME / "skills" / "mail-triage.md"

PIPELINE_COLUMNS = {
    "focus": "a0000000-0000-0000-0000-000000000001",
    "this_week": "a0000000-0000-0000-0000-000000000002",
    "next_week": "a0000000-0000-0000-0000-000000000003",
    "this_month": "a0000000-0000-0000-0000-000000000005",
}


def _get_litellm_url() -> str:
    return os.environ.get("TP_LITELLM_URL", "http://localhost:4000/v1")


def _get_default_model() -> str:
    return os.environ.get("TP_DEFAULT_MODEL", "ollama/qwen3.5:35b")


def _init_agent():
    """Erstellt den persistenten Hermes AIAgent (einmalig beim Worker-Start)."""
    global _agent
    if _agent is not None:
        return _agent

    sys.path.insert(0, str(Path(sys.prefix) / "lib" / "python3.12" / "site-packages"))

    from run_agent import AIAgent

    config_path = HERMES_HOME / "config.yaml"
    logger.info("Initialisiere Hermes Agent (config: %s)", config_path)

    _agent = AIAgent(
        model=_get_default_model(),
        base_url=_get_litellm_url(),
        api_key=os.environ.get("TP_LITELLM_API_KEY", "sk-litellm-local"),
        quiet_mode=True,
        max_iterations=50,
        reasoning_config={"enabled": False},
    )

    logger.info("Hermes Agent initialisiert (model=%s, base_url=%s)",
                _agent.model, _get_litellm_url())
    return _agent


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
    """Baut den Prompt für einen email_triage Job aus Metadata."""
    skill_text = _load_triage_skill()
    projects_context = await _load_projects_context()

    custom_triage_prompt = ""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(User.settings).where(User.role == "owner").limit(1)
            )
            owner_settings = result.scalar_one_or_none() or {}
        custom_triage_prompt = (owner_settings.get("triage_prompt") or "").strip()
    except Exception:
        logger.warning("Konnte triage_prompt nicht aus User-Settings laden")

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
""" + (f"\n\n## ZUSÄTZLICHE BENUTZER-REGELN (haben Vorrang!)\n{custom_triage_prompt}" if custom_triage_prompt else "")


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
    """Deterministische Post-Processing-Logik nach LLM-Klassifikation."""
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

    if triage_class == "quick_response":
        triage_class = "auto_reply"
    elif triage_class == "board_task":
        triage_class = "task"
        reply_expected = True
    elif triage_class == "bedenkzeit":
        triage_class = "task"

    if draft_id and triage_class != "auto_reply":
        logger.warning("Job %s: draft_id vorhanden aber triage_class=%s, korrigiere zu auto_reply", job_id, triage_class)
        triage_class = "auto_reply"

    if triage_class == "auto_reply" and not draft_id:
        logger.warning("Job %s: auto_reply ohne draft_id, Fallback auf task", job_id)
        triage_class = "task"
        if not task_title:
            task_title = meta.get("subject", "E-Mail Triage")

    if triage_class == "task" and not task_title:
        task_title = meta.get("subject", "E-Mail Triage (kein Titel)")
        logger.warning("Job %s: task ohne task_title, verwende Subject: %s", job_id, task_title)

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


async def _populate_env_from_db() -> None:
    """Liest API-Tokens aus den User-Settings (Owner) und setzt sie als Env-Vars."""
    from app.config import get_settings

    _ENV_KEYS: dict[str, str] = {
        "pipedrive_api_token": "TP_PIPEDRIVE_API_TOKEN",
        "pipedrive_domain": "TP_PIPEDRIVE_DOMAIN",
        "toggl_api_token": "TP_TOGGL_API_TOKEN",
        "toggl_workspace_id": "TP_TOGGL_WORKSPACE_ID",
        "bexio_api_token": "TP_BEXIO_API_TOKEN",
        "invoiceinsight_api_key": "TP_INVOICEINSIGHT_API_KEY",
        "invoiceinsight_url": "TP_INVOICEINSIGHT_URL",
        "tavily_api_key": "TP_TAVILY_API_KEY",
    }

    cfg = get_settings()

    try:
        async with async_session() as db:
            result = await db.execute(
                select(User.settings).where(User.role == "owner").limit(1)
            )
            settings = result.scalar_one_or_none() or {}

        for db_key, env_key in _ENV_KEYS.items():
            if os.environ.get(env_key):
                continue
            value = settings.get(db_key, "") or getattr(cfg, db_key, "")
            if value:
                os.environ[env_key] = str(value)
            else:
                os.environ[env_key] = ""

        _SIGNA_MAP = {
            "isi_host": "TP_ISI_HOST",
            "isi_db": "TP_ISI_DB",
            "isi_user": "TP_ISI_USER",
            "isi_secret": "TP_ISI_SECRET",
        }
        for cfg_key, env_key in _SIGNA_MAP.items():
            if not os.environ.get(env_key):
                value = getattr(cfg, cfg_key, "")
                os.environ[env_key] = str(value) if value else ""
    except Exception:
        logger.warning("DB-Settings konnten nicht gelesen werden — Env-Vars bleiben wie sie sind")


async def _process_job(job_id, job_type: str, prompt: str, meta: dict) -> None:
    """Verarbeitet einen einzelnen AgentJob via Hermes AIAgent."""
    agent = _init_agent()
    logger.info("Starte Job %s (type=%s)", job_id, job_type)

    async with async_session() as db:
        await db.execute(
            update(AgentJob)
            .where(AgentJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    llm_model = meta.get("llm_model") or _get_default_model()
    if agent.model != llm_model:
        agent.model = llm_model
        logger.info("Job %s: Model-Switch → %s", job_id, llm_model)

    try:
        result = await asyncio.to_thread(agent.chat, prompt)
        content = result or ""
        if hasattr(result, "content"):
            content = result.content or ""
        logger.info("Job %s abgeschlossen: %s", job_id, str(content)[:200])

        if job_type == "email_triage":
            status = await _post_process_triage(job_id, str(content), meta)
        else:
            status = "completed"
            if "awaiting_approval" in str(content).lower():
                status = "awaiting_approval"

        async with async_session() as db:
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status=status,
                    output=str(content)[:4000],
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


_TOOL_CALL_RENDERERS: dict[str, callable] = {
    "clarify": lambda args: args.get("question", ""),
    "ask_user": lambda args: args.get("question", args.get("message", "")),
    "user_confirmation": lambda args: args.get("message", ""),
}


def _extract_readable_content(content: str) -> str:
    """Wandelt Tool-Call-JSON (z.B. clarify) in lesbaren Text um.

    Erkennt sowohl einzelne Tool-Calls als auch Arrays.
    Unbekannte Tool-Calls werden als 'Tool: <name>' zusammengefasst.
    """
    stripped = content.strip()
    if not stripped or stripped[0] not in ("{", "["):
        return content

    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return content

    calls = [parsed] if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
    if not calls or not all(isinstance(c, dict) and "name" in c for c in calls):
        return content

    parts = []
    for call in calls:
        name = call.get("name", "")
        args = call.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}

        renderer = _TOOL_CALL_RENDERERS.get(name)
        if renderer:
            text = renderer(args)
            if text:
                parts.append(text)
        else:
            parts.append(f"*Tool ausgeführt: {name}*")

    return "\n\n".join(parts) if parts else content


async def _process_chat_job(job_id, prompt: str, meta: dict, pg_conn) -> None:
    """Verarbeitet einen Chat-Job mit Streaming via PG NOTIFY."""
    agent = _init_agent()
    job_id_str = str(job_id)

    async with async_session() as db:
        await db.execute(
            update(AgentJob)
            .where(AgentJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    llm_model = meta.get("llm_model") or _get_default_model()
    if agent.model != llm_model:
        agent.model = llm_model
        logger.info("Chat-Job %s: Model-Switch → %s", job_id, llm_model)

    stream_channel = f"chat_stream_{job_id_str.replace('-', '')}"
    buffer = []
    last_flush = time.monotonic()
    MAX_NOTIFY_BYTES = 7500

    def _send_chunk(text: str):
        """Sendet einen Chunk per pg_notify(), splittet bei Überschreitung des PG-Limits."""
        payload = json.dumps({"type": "chunk", "content": text}, ensure_ascii=False)
        if len(payload.encode("utf-8")) <= MAX_NOTIFY_BYTES:
            pg_conn.execute("SELECT pg_notify(%s, %s)", [stream_channel, payload])
            return
        mid = len(text) // 2
        _send_chunk(text[:mid])
        _send_chunk(text[mid:])

    def _flush_buffer():
        nonlocal last_flush
        if buffer:
            chunk = "".join(buffer)
            buffer.clear()
            try:
                _send_chunk(chunk)
            except Exception as e:
                logger.warning("NOTIFY fehlgeschlagen: %s", e)
            last_flush = time.monotonic()

    def on_stream_delta(text: str):
        buffer.append(text)
        if time.monotonic() - last_flush > 0.5 or len("".join(buffer)) > 200:
            _flush_buffer()

    def _run_sync():
        """Synchroner Block: agent.chat + NOTIFY (läuft in separatem Thread)."""
        result = agent.chat(prompt, stream_callback=on_stream_delta)
        _flush_buffer()

        content = result or ""
        if hasattr(result, "content"):
            content = result.content or ""
        content = str(content)

        readable = _extract_readable_content(content)
        if readable != content:
            clear_payload = json.dumps({"type": "clear"}, ensure_ascii=False)
            pg_conn.execute("SELECT pg_notify(%s, %s)", [stream_channel, clear_payload])
            _send_chunk(readable)

        done_payload = json.dumps({"type": "done"}, ensure_ascii=False)
        pg_conn.execute("SELECT pg_notify(%s, %s)", [stream_channel, done_payload])
        return readable

    try:
        content = await asyncio.to_thread(_run_sync)

        async with async_session() as db:
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status="completed",
                    output=content,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        logger.info("Chat-Job %s abgeschlossen (%d Zeichen)", job_id, len(content))

    except Exception as e:
        logger.exception("Chat-Job %s fehlgeschlagen", job_id)
        error_msg = str(e)[:500]
        error_payload = json.dumps({"type": "error", "error": error_msg}, ensure_ascii=False)
        try:
            pg_conn.execute("SELECT pg_notify(%s, %s)", [stream_channel, error_payload])
        except Exception:
            pass

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
            await db.commit()


async def _cleanup_orphaned_drafts() -> int:
    """Schliesst awaiting_approval-Jobs ab, deren Draft in Outlook nicht mehr existiert."""
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
    from graph_client import GraphClient, GraphConfig
    from app.config import get_settings

    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return 0

    async with async_session() as db:
        result = await db.execute(
            select(AgentJob).where(
                AgentJob.status == "awaiting_approval",
                AgentJob.job_type.in_(["email_triage", "send_email"]),
            )
        )
        jobs = list(result.scalars().all())

    if not jobs:
        return 0

    config = GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    )
    client = GraphClient(config)
    resolved = 0

    try:
        for job in jobs:
            meta = job.metadata_json or {}
            draft_id = meta.get("draft_id")
            if not draft_id:
                continue
            try:
                await client.get_email(draft_id)
            except Exception:
                async with async_session() as db:
                    await db.execute(
                        update(AgentJob)
                        .where(AgentJob.id == job.id)
                        .values(
                            status="completed",
                            output=(job.output or "") + "\n\n--- Entwurf wurde in Outlook gesendet oder gelöscht. Job automatisch abgeschlossen. ---",
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.commit()
                resolved += 1
                logger.info("Draft-Cleanup: Job %s automatisch abgeschlossen (Draft nicht mehr in Outlook)", job.id)
    finally:
        await client.close()

    if resolved:
        logger.info("Draft-Cleanup: %d verwaiste Jobs abgeschlossen", resolved)
    return resolved


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


def _get_pg_dsn() -> str:
    """Baut DSN aus Env-Vars."""
    host = os.environ.get("TP_DB_HOST", "localhost")
    port = os.environ.get("TP_DB_PORT", "5435")
    user = os.environ.get("TP_DB_USER", "taskpilot")
    password = os.environ.get("TP_DB_PASSWORD", "taskpilot_dev_2026")
    dbname = os.environ.get("TP_DB_NAME", "taskpilot_dev")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


async def _cleanup_stale_running_jobs() -> None:
    """Setzt verwaiste running-Jobs nach Worker-Neustart auf failed."""
    async with async_session() as db:
        result = await db.execute(
            update(AgentJob)
            .where(AgentJob.status == "running")
            .values(
                status="failed",
                error_message="Durch Worker-Neustart abgebrochen",
                completed_at=datetime.now(timezone.utc),
            )
            .returning(AgentJob.id)
        )
        stale_ids = result.scalars().all()
        if stale_ids:
            logger.warning(
                "Startup-Cleanup: %d verwaiste running-Jobs auf failed gesetzt: %s",
                len(stale_ids), [str(i) for i in stale_ids],
            )
        await db.commit()


async def _worker_loop() -> None:
    """Pollt nach queued Jobs und verarbeitet sie sequentiell."""
    await asyncio.sleep(3)

    await _cleanup_stale_running_jobs()
    await _populate_env_from_db()

    _init_agent()
    logger.info("Hermes-Worker gestartet -- pollt alle %ds nach queued Jobs", POLL_INTERVAL)

    last_reap = time.monotonic()
    last_draft_cleanup = time.monotonic()

    while True:
        try:
            if time.monotonic() - last_reap >= REAP_INTERVAL:
                await _reap_stale_jobs()
                last_reap = time.monotonic()

            if time.monotonic() - last_draft_cleanup >= DRAFT_CLEANUP_INTERVAL:
                try:
                    await _cleanup_orphaned_drafts()
                except Exception:
                    logger.exception("Draft-Cleanup fehlgeschlagen")
                last_draft_cleanup = time.monotonic()

            async with async_session() as db:
                result = await db.execute(
                    select(AgentJob)
                    .where(
                        AgentJob.status == "queued",
                        AgentJob.job_type != "chat_agent",
                    )
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

                await _process_job(job.id, job.job_type or "generic", prompt, meta)
            else:
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Hermes-Worker: unerwarteter Fehler")
            await asyncio.sleep(POLL_INTERVAL)


CHAT_SWEEP_INTERVAL = 30


async def _sweep_orphaned_chat_jobs(pg_conn) -> int:
    """Findet und verarbeitet verwaiste queued chat_agent Jobs."""
    async with async_session() as db:
        result = await db.execute(
            select(AgentJob)
            .where(
                AgentJob.status == "queued",
                AgentJob.job_type == "chat_agent",
                AgentJob.created_at < datetime.now(timezone.utc) - timedelta(seconds=10),
            )
            .order_by(AgentJob.created_at)
        )
        orphans = result.scalars().all()

    for job in orphans:
        try:
            meta = job.metadata_json or {}
            prompt = meta.get("prompt", "")
            logger.info("Chat-Sweep: verwaisten Job %s aufgenommen", job.id)
            await _process_chat_job(job.id, prompt, meta, pg_conn)
        except Exception:
            logger.exception("Chat-Sweep: Fehler bei Job %s", job.id)
    return len(orphans)


async def _chat_listener_loop() -> None:
    """Lauscht auf PG NOTIFY für Chat-Jobs, mit periodischem Sweep als Fallback."""
    await asyncio.sleep(4)

    dsn = _get_pg_dsn()
    notify_conn = None
    pg_conn = None

    while True:
        try:
            notify_conn = await psycopg.AsyncConnection.connect(
                dsn, autocommit=True
            )
            pg_conn = psycopg.connect(dsn, autocommit=True)

            await notify_conn.execute("LISTEN chat_job_dispatch")
            logger.info("Chat-Listener: LISTEN chat_job_dispatch aktiv")

            swept = await _sweep_orphaned_chat_jobs(pg_conn)
            if swept:
                logger.info("Chat-Listener: %d verwaiste Jobs beim Start verarbeitet", swept)

            gen = notify_conn.notifies()
            last_sweep = time.monotonic()

            while True:
                try:
                    notify = await asyncio.wait_for(
                        gen.__anext__(), timeout=CHAT_SWEEP_INTERVAL
                    )
                except (asyncio.TimeoutError, StopAsyncIteration):
                    if time.monotonic() - last_sweep >= CHAT_SWEEP_INTERVAL:
                        await _sweep_orphaned_chat_jobs(pg_conn)
                        last_sweep = time.monotonic()
                    continue

                try:
                    data = json.loads(notify.payload)
                    job_id = data.get("job_id")
                    if not job_id:
                        continue

                    async with async_session() as db:
                        result = await db.execute(
                            select(AgentJob).where(AgentJob.id == job_id)
                        )
                        job = result.scalar_one_or_none()

                    if job and job.status == "queued":
                        meta = job.metadata_json or {}
                        prompt = meta.get("prompt", "")
                        await _process_chat_job(job.id, prompt, meta, pg_conn)

                except Exception:
                    logger.exception("Chat-Listener: Fehler bei Job-Verarbeitung")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Chat-Listener: Verbindungsfehler, Reconnect in 5s")
            await asyncio.sleep(5)
        finally:
            if notify_conn:
                await notify_conn.close()
            if pg_conn:
                pg_conn.close()


async def start_hermes_worker() -> None:
    """Startet den Hermes-Worker als Hintergrund-Task."""
    global _worker_task, _listener_task
    _worker_task = asyncio.create_task(_worker_loop())
    _listener_task = asyncio.create_task(_chat_listener_loop())
    logger.info("Hermes-Worker: Hintergrund-Tasks gestartet")


async def stop_hermes_worker() -> None:
    """Stoppt den Hermes-Worker und gibt Ressourcen frei."""
    global _worker_task, _listener_task, _agent
    for task in (_worker_task, _listener_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _worker_task = None
    _listener_task = None
    _agent = None
    logger.info("Hermes-Worker gestoppt, Agent freigegeben")


if __name__ == "__main__":
    import signal

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    async def _run() -> None:
        """Startet Worker-Loop und Chat-Listener als eigenständiger Prozess."""
        loop = asyncio.get_running_loop()

        def _handle_signal() -> None:
            logger.info("Shutdown-Signal empfangen, Worker wird gestoppt...")
            for task in asyncio.all_tasks(loop):
                task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)

        logger.info(
            "Hermes Worker startet als eigenständiger Prozess (PID=%d)", os.getpid()
        )

        try:
            await asyncio.gather(
                _worker_loop(),
                _chat_listener_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Worker-Tasks beendet")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass

    logger.info("Hermes Worker beendet (PID=%d)", os.getpid())
