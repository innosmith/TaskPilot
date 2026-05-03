"""Router für LLM-Chat-Konversationen mit Streaming via litellm."""

import asyncio
import json
import logging
import os
import time
import uuid

import litellm
import markdown as md_lib
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db, async_session
from app.models import AgentJob, BoardColumn, Project, Task, User
from app.models.models import LlmConversation, LlmMessage

litellm.drop_params = True

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/conversations")
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    task_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alle Konversationen (paginiert, neueste zuerst).

    Eine kombinierte Abfrage mit korrelierten Subqueries vermeidet N+1.
    """

    msg_count_sq = (
        select(func.count())
        .select_from(LlmMessage)
        .where(LlmMessage.conversation_id == LlmConversation.id)
        .scalar_subquery()
        .label("msg_count")
    )

    last_preview_sq = (
        select(func.substr(LlmMessage.content, 1, 125))
        .where(LlmMessage.conversation_id == LlmConversation.id)
        .order_by(LlmMessage.created_at.desc())
        .limit(1)
        .scalar_subquery()
        .label("last_preview")
    )

    count_q = select(func.count()).select_from(LlmConversation)
    if task_id:
        count_q = count_q.where(LlmConversation.task_id == task_id)
    total = (await db.execute(count_q)).scalar_one()

    q = (
        select(LlmConversation, msg_count_sq, last_preview_sq)
        .order_by(LlmConversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if task_id:
        q = q.where(LlmConversation.task_id == task_id)

    result = await db.execute(q)

    items = []
    for row in result.all():
        conv = row[0]
        msg_count = row[1] or 0
        last_raw = row[2]
        last_preview = None
        if last_raw:
            last_preview = (last_raw[:120] + "...") if len(last_raw) > 120 else last_raw

        items.append({
            "id": str(conv.id),
            "title": conv.title,
            "task_id": str(conv.task_id) if conv.task_id else None,
            "model": conv.model,
            "mode": conv.mode,
            "total_tokens": conv.total_tokens,
            "total_cost_usd": float(conv.total_cost_usd),
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "message_count": msg_count,
            "last_message_preview": last_preview,
        })

    return {"items": items, "total": total}


@router.post("/conversations")
async def create_conversation(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Neue Konversation erstellen."""
    settings = user.settings or {}
    default_model = settings.get("llm_default_model", "ollama/qwen3.5:35b")
    default_temp = settings.get("llm_default_temperature", 0.7)

    conv = LlmConversation(
        title=body.get("title"),
        task_id=body.get("task_id"),
        model=body.get("model", default_model),
        mode=body.get("mode", "chat"),
        temperature=body.get("temperature", default_temp),
    )
    db.add(conv)
    await db.flush()
    return {
        "id": str(conv.id),
        "title": conv.title,
        "task_id": str(conv.task_id) if conv.task_id else None,
        "model": conv.model,
        "mode": conv.mode,
        "temperature": conv.temperature,
        "total_tokens": conv.total_tokens,
        "total_cost_usd": float(conv.total_cost_usd),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.delete("/conversations")
async def delete_all_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alle Chat-Konversationen löschen (Nachrichten per ON DELETE CASCADE)."""
    res = await db.execute(delete(LlmConversation))
    return {"ok": True, "deleted": res.rowcount or 0}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Konversation mit allen Nachrichten laden."""
    result = await db.execute(
        select(LlmConversation)
        .options(selectinload(LlmConversation.messages))
        .where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    return {
        "id": str(conv.id),
        "title": conv.title,
        "task_id": str(conv.task_id) if conv.task_id else None,
        "model": conv.model,
        "mode": conv.mode,
        "temperature": conv.temperature,
        "total_tokens": conv.total_tokens,
        "total_cost_usd": float(conv.total_cost_usd),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "messages": [
            {
                "id": str(msg.id),
                "conversation_id": str(msg.conversation_id),
                "role": msg.role,
                "content": msg.content,
                "model": msg.model,
                "tokens": msg.tokens,
                "cost_usd": float(msg.cost_usd) if msg.cost_usd else None,
                "attachments": msg.attachments,
                "citations": msg.citations,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in conv.messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Konversation löschen."""
    result = await db.execute(
        select(LlmConversation).where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")
    await db.delete(conv)
    return {"ok": True}


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Konversation aktualisieren (Titel, Modell, Temperatur)."""
    result = await db.execute(
        select(LlmConversation).where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    if "title" in body:
        conv.title = body["title"]
    if "model" in body:
        conv.model = body["model"]
    if "temperature" in body:
        conv.temperature = body["temperature"]
    if "mode" in body:
        conv.mode = body["mode"]

    await db.flush()
    return {
        "id": str(conv.id),
        "title": conv.title,
        "model": conv.model,
        "mode": conv.mode,
        "temperature": conv.temperature,
    }


@router.post("/conversations/{conversation_id}/messages/batch")
async def batch_save_messages(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mehrere Nachrichten synchron speichern (fuer Web-Suche etc.)."""
    result = await db.execute(
        select(LlmConversation).where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    messages_data = body.get("messages", [])
    saved = []
    for m in messages_data:
        msg = LlmMessage(
            conversation_id=conv.id,
            role=m.get("role", "user"),
            content=m.get("content", ""),
            tokens=m.get("tokens"),
            cost_usd=m.get("cost_usd"),
            citations=m.get("citations", []),
        )
        db.add(msg)
        await db.flush()
        saved.append({"id": str(msg.id), "role": msg.role})

    if not conv.title and messages_data:
        first_user = next((m for m in messages_data if m.get("role") == "user"), None)
        if first_user:
            conv.title = (first_user["content"][:80] + "...") if len(first_user["content"]) > 80 else first_user["content"]

    return {"ok": True, "saved": saved}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nachricht senden und LLM-Antwort als SSE streamen."""
    result = await db.execute(
        select(LlmConversation)
        .options(selectinload(LlmConversation.messages))
        .where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    user_content = body.get("content", "")
    user_attachments = body.get("attachments", [])

    user_msg = LlmMessage(
        conversation_id=conv.id,
        role="user",
        content=user_content,
        attachments=user_attachments,
    )
    db.add(user_msg)
    await db.flush()

    if not conv.title and len(conv.messages) <= 1:
        conv.title = user_content[:80] + ("..." if len(user_content) > 80 else "")

    messages_for_llm = []
    for msg in conv.messages:
        messages_for_llm.append({"role": msg.role, "content": msg.content})
    messages_for_llm.append({"role": "user", "content": user_content})

    await db.commit()

    conv_id_str = str(conv.id)
    model = conv.model
    temperature = conv.temperature

    def _setup_api_keys():
        """API-Keys als Env-Vars setzen, damit litellm sie findet."""
        s = get_settings()
        if s.openai_api_key:
            os.environ["OPENAI_API_KEY"] = s.openai_api_key
        if s.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = s.anthropic_api_key
        if s.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = s.gemini_api_key
        if s.perplexity_api_key:
            os.environ["PERPLEXITYAI_API_KEY"] = s.perplexity_api_key

    def _is_gemini_deep_research(m: str) -> bool:
        return m.startswith("gemini/deep-research") or m in (
            "deep-research-preview-04-2026",
            "deep-research-max-preview-04-2026",
        )

    async def generate_gemini_research():
        """Gemini Deep Research via Interactions API."""
        from app.services.gemini_research import stream_research

        full_response = ""
        full_thinking = ""
        gemini_model = model.replace("gemini/", "") if model.startswith("gemini/") else None

        try:
            async for event in stream_research(user_content, model=gemini_model):
                if event["type"] == "thought":
                    full_thinking += event["content"] + "\n"
                    yield {"event": "thinking", "data": json.dumps({"content": event["content"]})}
                elif event["type"] == "text":
                    full_response += event["content"]
                    yield {"event": "chunk", "data": json.dumps({"content": event["content"]})}
                elif event["type"] == "status":
                    yield {"event": "status", "data": json.dumps({"content": event["content"]})}
                elif event["type"] == "error":
                    yield {"event": "error", "data": json.dumps({"error": event["content"]})}
                    return
                elif event["type"] == "done":
                    if event.get("content") and not full_response:
                        full_response = event["content"]
        except Exception as e:
            logger.exception("Gemini Deep Research Fehler")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            return

        async with async_session() as save_db:
            assistant_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content=full_response,
                tokens=0,
                cost_usd=None,
            )
            save_db.add(assistant_msg)
            await save_db.commit()

        yield {
            "event": "done",
            "data": json.dumps({
                "message_id": str(assistant_msg.id),
                "tokens": 0,
                "reasoning_tokens": 0,
                "cost_usd": None,
                "content": full_response,
                "thinking": full_thinking.strip() if full_thinking else None,
            }),
        }

    if _is_gemini_deep_research(model):
        return EventSourceResponse(generate_gemini_research())

    async def generate():
        _setup_api_keys()
        full_response = ""
        full_thinking = ""
        total_tokens_used = 0
        reasoning_tokens = 0
        cost_usd = 0.0

        extra_params: dict = {}
        if model.startswith("anthropic/"):
            extra_params["thinking"] = {"type": "enabled", "budget_tokens": 8192}
        elif model.startswith("gemini/"):
            extra_params["thinking"] = {"type": "enabled"}

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages_for_llm,
                temperature=temperature if not extra_params.get("thinking") else 1.0,
                stream=True,
                api_base="http://localhost:11434" if model.startswith("ollama/") else None,
                **extra_params,
            )

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta:
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        full_thinking += rc
                        yield {
                            "event": "thinking",
                            "data": json.dumps({"content": rc}),
                        }
                    if delta.content:
                        full_response += delta.content
                        yield {
                            "event": "chunk",
                            "data": json.dumps({"content": delta.content}),
                        }
                if hasattr(chunk, "usage") and chunk.usage:
                    total_tokens_used = getattr(chunk.usage, "total_tokens", 0) or 0
                    details = getattr(chunk.usage, "completion_tokens_details", None)
                    if details:
                        reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        except Exception as e:
            logger.exception("Streaming-Fehler mit Modell %s", model)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
            return

        try:
            cost_usd = litellm.cost_calculator.completion_cost(
                model=model,
                prompt=str(messages_for_llm),
                completion=full_response,
            )
        except Exception:
            pass

        # <think>-Tags aus dem Content separieren (Perplexity Deep Research)
        import re
        clean_response = full_response
        think_match = re.search(r"<think>(.*?)</think>", full_response, re.DOTALL)
        if think_match:
            if not full_thinking:
                full_thinking = think_match.group(1).strip()
            clean_response = re.sub(r"<think>.*?</think>\s*", "", full_response, flags=re.DOTALL).strip()

        async with async_session() as save_db:
            assistant_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content=clean_response,
                model=model,
                tokens=total_tokens_used,
                cost_usd=cost_usd if cost_usd > 0 else None,
            )
            save_db.add(assistant_msg)

            update_result = await save_db.execute(
                select(LlmConversation).where(LlmConversation.id == uuid.UUID(conv_id_str))
            )
            conv_update = update_result.scalar_one_or_none()
            if conv_update:
                conv_update.total_tokens = (conv_update.total_tokens or 0) + total_tokens_used
                conv_update.total_cost_usd = float(conv_update.total_cost_usd or 0) + cost_usd
            await save_db.commit()

        yield {
            "event": "done",
            "data": json.dumps({
                "message_id": str(assistant_msg.id),
                "tokens": total_tokens_used,
                "reasoning_tokens": reasoning_tokens,
                "cost_usd": round(cost_usd, 6) if cost_usd > 0 else None,
                "content": clean_response,
                "thinking": full_thinking if full_thinking else None,
                "model": model,
            }),
        }

    return EventSourceResponse(generate())


@router.post("/messages/{message_id}/create-task")
async def create_task_from_message(
    message_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt eine neue Aufgabe basierend auf einer Chat-Nachricht."""
    result = await db.execute(select(LlmMessage).where(LlmMessage.id == message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")

    project_id = body.get("project_id")
    board_column_id = body.get("board_column_id")

    if not project_id or not board_column_id:
        proj_result = await db.execute(
            select(Project).where(Project.status == "active").order_by(Project.created_at).limit(1)
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=400, detail="Kein aktives Projekt vorhanden")
        if not project_id:
            project_id = project.id

        col_result = await db.execute(
            select(BoardColumn)
            .where(BoardColumn.project_id == project_id)
            .order_by(BoardColumn.position)
            .limit(1)
        )
        column = col_result.scalar_one_or_none()
        if not column:
            raise HTTPException(status_code=400, detail="Keine Board-Spalte vorhanden")
        if not board_column_id:
            board_column_id = column.id

    max_pos_result = await db.execute(
        select(Task.board_position)
        .where(Task.board_column_id == board_column_id)
        .order_by(Task.board_position.desc())
        .limit(1)
    )
    max_pos = max_pos_result.scalar_one_or_none() or 0.0

    title = body.get("title") or message.content[:80]
    if len(message.content) > 80 and not body.get("title"):
        title += "..."

    raw_description = body.get("description", message.content)
    html_description = md_lib.markdown(
        raw_description,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )

    task = Task(
        title=title,
        description=html_description,
        project_id=project_id,
        board_column_id=board_column_id,
        board_position=max_pos + 1.0,
        assignee=body.get("assignee", "me"),
        due_date=body.get("due_date"),
    )
    db.add(task)
    await db.flush()

    return {"task_id": str(task.id), "title": task.title, "project_id": str(project_id)}


MAX_AGENT_TIMEOUT = 600
_NANOBOT_HOME = os.path.expanduser("~/.nanobot")
_NANOBOT_CONFIG = os.path.join(_NANOBOT_HOME, "config.json")

# ── Agent-Event-Buffer (Background-Decoupling) ──────────────────
# Jeder laufende/kürzlich beendete Agent-Run hat eine Event-Liste.
# Neue Subscriber bekommen alle Events ab einem Offset.

_agent_events: dict[str, list[dict]] = {}
_agent_conditions: dict[str, asyncio.Condition] = {}
_agent_running: dict[str, bool] = {}
_AGENT_EVENT_TTL = 600  # Events 10min nach Abschluss aufbewahren


async def _push_agent_event(job_id: str, event: dict):
    """Event in den Buffer schreiben und wartende Subscriber benachrichtigen."""
    if job_id not in _agent_events:
        _agent_events[job_id] = []
    _agent_events[job_id].append(event)
    cond = _agent_conditions.get(job_id)
    if cond:
        async with cond:
            cond.notify_all()


async def _cleanup_agent_events(job_id: str):
    """Events nach TTL aufräumen."""
    await asyncio.sleep(_AGENT_EVENT_TTL)
    _agent_events.pop(job_id, None)
    _agent_conditions.pop(job_id, None)
    _agent_running.pop(job_id, None)


def _load_agent_skills() -> str:
    """Lädt alle .md-Skill-Dateien dynamisch aus dem Nanobot-Workspace."""
    from pathlib import Path

    skills_dir = Path(os.environ.get(
        "TP_NANOBOT_WORKSPACE",
        os.path.expanduser("~/.nanobot/workspace"),
    )) / "skills"

    if not skills_dir.exists():
        return ""

    parts = []
    for path in sorted(skills_dir.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(parts)


MCP_SERVER_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "graph": {
        "label": "Microsoft 365",
        "description": "E-Mail, Kalender, Teams-Nachrichten, OneDrive, Dateisuche, Planner",
        "tools": (
            "search_drive(query) — Dateien auf OneDrive suchen; "
            "download_file(item_id) — Datei herunterladen und Text extrahieren (PDF); "
            "list_drive_items(path) — Ordnerinhalt auflisten; "
            "get_email(message_id) — E-Mail lesen; "
            "search_emails(query) — E-Mails durchsuchen; "
            "list_events(start, end) — Kalendereinträge; "
            "list_chats() — Teams-Chats; "
            "list_planner_tasks() — Planner-Aufgaben"
        ),
    },
    "taskpilot": {
        "label": "Aufgaben",
        "description": "Tasks erstellen, aktualisieren, zuweisen, Projekte verwalten",
        "tools": (
            "list_tasks(project_id, status) — Aufgaben auflisten; "
            "create_task(title, project_id) — Aufgabe erstellen; "
            "update_task(task_id, status) — Aufgabe ändern"
        ),
    },
    "pipedrive": {
        "label": "CRM (Pipedrive)",
        "description": "Deals, Kontakte, Aktivitäten, Notizen",
        "tools": (
            "list_deals() — Deals auflisten; "
            "get_deal(id) — Deal-Details; "
            "list_persons() — Kontakte; "
            "list_activities() — Aktivitäten"
        ),
    },
    "toggl": {
        "label": "Zeiterfassung (Toggl)",
        "description": "Zeiteinträge verwalten",
        "tools": (
            "list_time_entries(start, end) — Zeiteinträge auflisten; "
            "list_projects() — Projekte; "
            "get_project_summary(project_id) — Zusammenfassung"
        ),
    },
    "bexio": {
        "label": "Buchhaltung (Bexio)",
        "description": "Rechnungen, Journal, Kontenplan, Bankkonten, Geschäftsjahre",
        "tools": (
            "list_invoices(status, year) — Rechnungen auflisten; "
            "get_invoice(id) — Rechnungsdetails; "
            "search_invoices(query) — Rechnungen suchen; "
            "get_journal(year, from_date, to_date) — Buchungsjournal; "
            "list_accounts() — Kontenplan; "
            "list_bank_accounts() — Bankkonten; "
            "get_business_years() — Geschäftsjahre"
        ),
    },
    "invoiceinsight": {
        "label": "Kreditoren-Analyse",
        "description": "KPIs, Zahlungen, Anomalien, Cashflow-Prognose",
        "tools": (
            "get_kpis() — Kennzahlen; "
            "get_upcoming_payments() — Anstehende Zahlungen; "
            "get_cost_distribution() — Kostenverteilung; "
            "get_cashflow_forecast() — Cashflow-Prognose; "
            "get_invoice_details(id) — Rechnungsdetails mit PDF-Pfad"
        ),
    },
    "signa": {
        "label": "Recherche (SIGNA)",
        "description": "ISI-Datenbank, wissenschaftliche Quellen",
        "tools": (
            "search_signals(query) — Signale durchsuchen; "
            "get_briefing(id) — Briefing lesen"
        ),
    },
}


def _get_configured_mcp_servers() -> dict:
    """Liest die MCP-Server-Liste aus der Nanobot-Config."""
    config_path = os.path.join(_NANOBOT_HOME, "config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("tools", {}).get("mcpServers", {})
    except Exception:
        return {}


def _build_agent_prompt(user_content: str, conversation_messages: list) -> str:
    """Baut einen schlanken Prompt — Tool-Definitionen kommen nativ vom Nanobot SDK via MCP."""
    skills_text = _load_agent_skills()

    history_lines = []
    for msg in conversation_messages[-10:]:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"**{role_label}:** {msg.content[:500]}")
    history_block = "\n\n".join(history_lines) if history_lines else "(Erste Nachricht)"

    return f"""Du bist InnoPilot, der KI-Agent von Anthony Smith (InnoSmith GmbH, Schweiz).
Du hast direkten Zugriff auf Firmendaten über deine MCP-Tools (siehst du in deiner Tool-Liste).
Nutze deine Tools aktiv. Behaupte niemals, du hättest keinen Zugriff.

Regeln:
- Bei Fragen zu Firmendaten: Sofort passende Tools aufrufen
- Dateien: search_files → download_file
- Buchhaltung: list_accounts, get_journal, list_invoices, search_invoices
- Mehrstufige Aufgaben: Schritt für Schritt, Tool-Ergebnisse auswerten
- Sprache: Deutsch (Schweizer Hochdeutsch, ss statt ß, korrekte Umlaute ä/ö/ü)
- Zeitzone: Europe/Zurich

## Skills

{skills_text}

## Chat-Verlauf

{history_block}

## Anfrage

{user_content}"""


@router.get("/agent-tools")
async def get_agent_tools(user: User = Depends(get_current_user)):
    """Gibt die konfigurierten MCP-Server mit Beschreibungen zurück."""
    servers = _get_configured_mcp_servers()
    result = []
    for key in servers:
        meta = MCP_SERVER_DESCRIPTIONS.get(key, {})
        result.append({
            "key": key,
            "label": meta.get("label", key.capitalize()),
            "description": meta.get("description", ""),
        })
    return {"servers": result}


@router.post("/conversations/{conversation_id}/agent")
async def send_agent_message(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent-Nachricht absenden — startet Background-Task, gibt job_id zurück.

    Der Agent läuft unabhängig vom Client. Events werden über
    GET /conversations/{id}/agent-stream?job_id=... gestreamt und
    können nach Reconnect ab beliebigem Offset fortgesetzt werden.
    """
    from datetime import datetime, timezone as tz

    logger.info("[agent] Anfrage für Konversation %s", conversation_id)

    result = await db.execute(
        select(LlmConversation)
        .options(selectinload(LlmConversation.messages))
        .where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    user_content = body.get("content", "")
    selected_model = body.get("model", "nanobot")
    logger.info("[agent] Nachricht (%.80s…), conv=%s", user_content, conversation_id)

    user_msg = LlmMessage(
        conversation_id=conv.id,
        role="user",
        content=user_content,
    )
    db.add(user_msg)
    await db.flush()

    if not conv.title and len(conv.messages) <= 1:
        conv.title = user_content[:80] + ("..." if len(user_content) > 80 else "")

    sorted_messages = sorted(conv.messages, key=lambda m: m.created_at)
    full_prompt = _build_agent_prompt(user_content, sorted_messages)

    agent_job = AgentJob(
        job_type="chat_agent",
        status="running",
        llm_model=selected_model,
        metadata_json={
            "conversation_id": str(conv.id),
            "prompt_preview": user_content[:200],
        },
        started_at=datetime.now(tz.utc),
    )
    db.add(agent_job)
    await db.flush()
    agent_job_id = agent_job.id

    await db.commit()
    conv_id_str = str(conv.id)
    job_id_str = str(agent_job_id)

    _agent_events[job_id_str] = []
    _agent_conditions[job_id_str] = asyncio.Condition()
    _agent_running[job_id_str] = True

    asyncio.create_task(
        _run_agent_background(job_id_str, conv_id_str, full_prompt, selected_model)
    )

    return {
        "job_id": job_id_str,
        "conversation_id": conv_id_str,
        "status": "running",
    }


OLLAMA_API_BASE = "http://localhost:11434/v1"
LITELLM_API_BASE = "http://localhost:4000/v1"


def _apply_model_routing(bot, selected_model: str) -> None:
    """Setzt Modell und Provider-Endpoint basierend auf User-Wahl.

    Modell-ID-Format aus Frontend: 'ollama/qwen3.5:35b', 'anthropic/claude-sonnet-4-6', etc.
    Für lokale Modelle → direkt Ollama. Für Cloud → LiteLLM-Proxy.
    """
    if not selected_model or selected_model == "nanobot":
        return

    if selected_model.startswith("ollama/"):
        bot._loop.model = selected_model.removeprefix("ollama/")
        bot._loop.provider.api_base = OLLAMA_API_BASE
    else:
        bot._loop.model = selected_model
        bot._loop.provider.api_base = LITELLM_API_BASE


async def _run_agent_background(
    job_id: str, conv_id: str, prompt: str, model: str
):
    """Führt den Nanobot-Agent als Background-Task aus, schreibt Events in den Buffer."""
    from datetime import datetime, timezone as tz
    from nanobot.agent.hook import AgentHook
    from app.services.nanobot_worker import _init_chat_bot, reset_chat_bot

    t_start = time.time()

    async def _update_agent_job(
        status: str,
        output: str | None = None,
        error_message: str | None = None,
        tools_used: list[str] | None = None,
    ):
        async with async_session() as sdb:
            res = await sdb.execute(
                select(AgentJob).where(AgentJob.id == uuid.UUID(job_id))
            )
            job = res.scalar_one_or_none()
            if not job:
                return
            job.status = status
            if output is not None:
                job.output = output[:2000]
            if error_message is not None:
                job.error_message = error_message
            if status in ("completed", "failed"):
                job.completed_at = datetime.now(tz.utc)
            if tools_used:
                meta = dict(job.metadata_json or {})
                meta["tools_used"] = tools_used
                job.metadata_json = meta
            await sdb.commit()

    queue: asyncio.Queue = asyncio.Queue()

    class BufferedHook(AgentHook):
        """Nanobot-Events in Queue schreiben (Background-safe)."""

        def wants_streaming(self) -> bool:
            return True

        async def on_stream(self, context, delta: str):
            await queue.put(("chunk", delta))

        async def on_stream_end(self, context, *, resuming: bool = False):
            if resuming:
                await queue.put(("status", "InnoPilot arbeitet weiter..."))

        async def before_execute_tools(self, context):
            tool_names = [tc.name for tc in (context.tool_calls or [])]
            if tool_names:
                await queue.put(("tool_start", ", ".join(tool_names)))

        async def after_iteration(self, context):
            for ev in (context.tool_events or []):
                await queue.put(("tool_event", json.dumps(ev, ensure_ascii=False)))

    await _push_agent_event(job_id, {"event": "status", "data": json.dumps({"content": "InnoPilot wird initialisiert..."})})
    await _push_agent_event(job_id, {"event": "status", "data": json.dumps({"content": "Agenten-Konfiguration und MCP-Server werden geladen..."})})

    try:
        bot = await _init_chat_bot()
    except Exception as e:
        logger.exception("[agent-bg] Bot-Init fehlgeschlagen")
        await _update_agent_job("failed", error_message=f"Init fehlgeschlagen: {e}")
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": f"InnoPilot konnte nicht initialisiert werden: {e}"})})
        _agent_running[job_id] = False
        asyncio.create_task(_cleanup_agent_events(job_id))
        return

    if bot is None:
        logger.error("[agent-bg] Chat-Bot nicht verfügbar")
        await _update_agent_job("failed", error_message="Bot nicht verfügbar")
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": "InnoPilot nicht verfügbar — prüfe ~/.nanobot/config.json"})})
        _agent_running[job_id] = False
        asyncio.create_task(_cleanup_agent_events(job_id))
        return

    session_key = f"chat:{conv_id}"
    hook = BufferedHook()

    _apply_model_routing(bot, model)

    mcp_count = len(getattr(bot._loop, '_mcp_servers', None) or {})
    active_model = getattr(bot._loop, 'model', '?')
    await _push_agent_event(job_id, {"event": "status", "data": json.dumps(
        {"content": f"InnoPilot bereit ({mcp_count} MCP-Server, Modell: {active_model}) — Aufgabe wird verarbeitet..."})})
    logger.info("[agent-bg] Run gestartet, session=%s, model=%s, prompt_len=%d, mcp_servers=%d",
                session_key, active_model, len(prompt), mcp_count)

    bot_task = asyncio.create_task(
        bot.run(prompt, session_key=session_key, hooks=[hook])
    )

    try:
        while not bot_task.done():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=2.0)
                evt_type, evt_data = item
                if evt_type == "chunk":
                    await _push_agent_event(job_id, {"event": "chunk", "data": json.dumps({"content": evt_data})})
                elif evt_type == "tool_start":
                    await _push_agent_event(job_id, {"event": "tool_start", "data": json.dumps({"tools": evt_data})})
                elif evt_type == "tool_event":
                    await _push_agent_event(job_id, {"event": "tool_event", "data": evt_data})
                elif evt_type == "status":
                    await _push_agent_event(job_id, {"event": "status", "data": json.dumps({"content": evt_data})})
            except asyncio.TimeoutError:
                elapsed = time.time() - t_start
                if elapsed > MAX_AGENT_TIMEOUT:
                    bot_task.cancel()
                    logger.warning("[agent-bg] Timeout nach %.0fs, job=%s", elapsed, job_id)
                    await _update_agent_job("failed", error_message=f"Timeout nach {MAX_AGENT_TIMEOUT}s")
                    await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": f"InnoPilot hat das Zeitlimit überschritten ({MAX_AGENT_TIMEOUT}s)"})})
                    _agent_running[job_id] = False
                    asyncio.create_task(_cleanup_agent_events(job_id))
                    return

        while not queue.empty():
            item = queue.get_nowait()
            evt_type, evt_data = item
            if evt_type == "chunk":
                await _push_agent_event(job_id, {"event": "chunk", "data": json.dumps({"content": evt_data})})
            elif evt_type == "tool_start":
                await _push_agent_event(job_id, {"event": "tool_start", "data": json.dumps({"tools": evt_data})})
            elif evt_type == "tool_event":
                await _push_agent_event(job_id, {"event": "tool_event", "data": evt_data})

        bot_result = bot_task.result()
        content = bot_result.content or ""
        tools_used = bot_result.tools_used or []
        elapsed = time.time() - t_start
        logger.info("[agent-bg] Fertig in %.1fs, Antwort=%d Zeichen, Tools=%s, job=%s",
                    elapsed, len(content), tools_used, job_id)

    except Exception as e:
        logger.exception("[agent-bg] Fehler in job=%s", job_id)
        reset_chat_bot()
        await _update_agent_job("failed", error_message=str(e))
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": f"InnoPilot-Fehler: {e}"})})
        _agent_running[job_id] = False
        asyncio.create_task(_cleanup_agent_events(job_id))
        return

    async with async_session() as save_db:
        assistant_msg = LlmMessage(
            conversation_id=uuid.UUID(conv_id),
            role="assistant",
            content=content,
        )
        save_db.add(assistant_msg)
        await save_db.commit()

    await _update_agent_job("completed", output=content, tools_used=tools_used)

    await _push_agent_event(job_id, {"event": "done", "data": json.dumps({
        "message_id": str(assistant_msg.id),
        "tokens": 0,
        "content": content,
        "tools_used": tools_used,
        "elapsed_s": round(time.time() - t_start, 1),
    })})

    _agent_running[job_id] = False
    asyncio.create_task(_cleanup_agent_events(job_id))


@router.get("/conversations/{conversation_id}/agent-stream")
async def stream_agent_events(
    conversation_id: uuid.UUID,
    job_id: str = Query(..., description="Agent-Job-ID aus POST-Antwort"),
    offset: int = Query(0, ge=0, description="Event-Offset für Reconnect"),
    user: User = Depends(get_current_user),
):
    """SSE-Stream der Agent-Events. Reconnect-fähig über offset-Parameter.

    Der Client verbindet sich nach dem POST hierhin und erhält alle Events
    ab dem angegebenen Offset. Bei Verbindungsverlust einfach mit dem
    letzten empfangenen Offset erneut verbinden.
    """
    if job_id not in _agent_events:
        raise HTTPException(status_code=404, detail="Agent-Job nicht gefunden oder bereits abgelaufen")

    async def generate():
        idx = offset
        while True:
            events = _agent_events.get(job_id, [])

            while idx < len(events):
                evt = events[idx]
                evt_with_idx = dict(evt)
                data = json.loads(evt.get("data", "{}"))
                data["_idx"] = idx
                evt_with_idx["data"] = json.dumps(data, ensure_ascii=False)
                yield evt_with_idx
                idx += 1

                if evt.get("event") in ("done", "error"):
                    return

            if not _agent_running.get(job_id, False):
                return

            cond = _agent_conditions.get(job_id)
            if cond:
                try:
                    async with cond:
                        await asyncio.wait_for(cond.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"ts": int(time.time())})}

    return EventSourceResponse(generate())
