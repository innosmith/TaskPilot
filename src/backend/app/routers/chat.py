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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db, async_session
from app.models import BoardColumn, Project, Task, User
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
    """Alle Konversationen (paginiert, neueste zuerst)."""
    query = select(LlmConversation).order_by(LlmConversation.updated_at.desc())
    if task_id:
        query = query.where(LlmConversation.task_id == task_id)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    conversations = result.scalars().all()

    items = []
    for conv in conversations:
        msg_count_result = await db.execute(
            select(func.count()).where(LlmMessage.conversation_id == conv.id)
        )
        msg_count = msg_count_result.scalar() or 0

        last_msg_result = await db.execute(
            select(LlmMessage.content)
            .where(LlmMessage.conversation_id == conv.id)
            .order_by(LlmMessage.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

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
            "last_message_preview": (last_msg[:120] + "...") if last_msg and len(last_msg) > 120 else last_msg,
        })

    return {"items": items, "total": len(items)}


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

    async def generate():
        _setup_api_keys()
        full_response = ""
        full_thinking = ""
        total_tokens_used = 0
        reasoning_tokens = 0
        cost_usd = 0.0

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages_for_llm,
                temperature=temperature,
                stream=True,
                api_base="http://localhost:11434" if model.startswith("ollama/") else None,
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

        async with async_session() as save_db:
            assistant_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content=full_response,
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
                "content": full_response,
                "thinking": full_thinking if full_thinking else None,
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


def _load_agent_skills() -> str:
    """Lädt alle Skills aus dem Nanobot-Workspace für den Chat-Agent."""
    from pathlib import Path

    skills_dir = Path(os.environ.get(
        "TP_NANOBOT_WORKSPACE",
        os.path.expanduser("~/.nanobot/workspace"),
    )) / "skills"

    if not skills_dir.exists():
        return ""

    skill_files = [
        "calendar-management.md",
        "crm-assistant.md",
        "signa-recherche.md",
    ]

    parts = []
    for fname in skill_files:
        path = skills_dir / fname
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(parts)


def _build_agent_prompt(user_content: str, conversation_messages: list) -> str:
    """Baut einen vollständigen Prompt mit System-Kontext, Skills und Chat-Verlauf."""
    skills_text = _load_agent_skills()

    history_lines = []
    for msg in conversation_messages[-10:]:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"**{role_label}:** {msg.content[:500]}")
    history_block = "\n\n".join(history_lines) if history_lines else "(Erste Nachricht)"

    return f"""## SYSTEM-KONTEXT

Du bist der TaskPilot-Agent von Anthony Smith (InnoSmith GmbH, Schweiz).
Du hast Zugriff auf MCP-Tools für E-Mail, Kalender, CRM, Aufgaben und mehr.
NUTZE DEINE TOOLS AKTIV! Behaupte NIEMALS, du hättest keinen Zugriff.

### Verfügbare MCP-Server und Tools:
- **email**: E-Mails lesen/schreiben, Kalender verwalten (list_calendar_events, create_calendar_event, find_free_slots, get_calendar_event)
- **taskpilot**: Aufgaben und Projekte verwalten (create_task, update_task, list_tasks, etc.)
- **pipedrive**: CRM-Daten (Deals, Kontakte, Aktivitäten)
- **toggl**: Zeiterfassung
- **bexio**: Buchhaltung
- **signa**: ISI-Datenbank

### Zeitzone: Europe/Zurich

---

## SKILLS

{skills_text}

---

## BISHERIGER CHAT-VERLAUF

{history_block}

---

## AKTUELLE ANFRAGE

{user_content}

---

Führe die Anfrage jetzt aus. Nutze die passenden MCP-Tools. Antworte auf Deutsch (Schweizer Hochdeutsch, kein ß)."""


@router.post("/conversations/{conversation_id}/agent")
async def send_agent_message(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nachricht an Nanobot senden — Agent hat Zugriff auf alle MCP-Tools."""
    logger.info("Agent-Endpoint aufgerufen für Konversation %s", conversation_id)

    result = await db.execute(
        select(LlmConversation)
        .options(selectinload(LlmConversation.messages))
        .where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        logger.warning("Konversation %s nicht gefunden", conversation_id)
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    user_content = body.get("content", "")
    logger.info("Agent-Nachricht erhalten: %.100s…", user_content)

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

    await db.commit()
    conv_id_str = str(conv.id)

    async def generate():
        from app.services.nanobot_worker import _init_bot

        yield {"event": "thinking", "data": json.dumps({"content": "Nanobot verarbeitet mit MCP-Tools..."})}

        logger.info("Nanobot-Init für Konversation %s", conv_id_str)
        try:
            bot = await _init_bot()
        except Exception as e:
            logger.exception("Nanobot-Init fehlgeschlagen")
            yield {"event": "error", "data": json.dumps({"error": f"Nanobot konnte nicht initialisiert werden: {e}"})}
            return

        if bot is None:
            logger.error("Nanobot SDK nicht verfügbar (bot=None)")
            yield {"event": "error", "data": json.dumps({"error": "Nanobot SDK nicht verfügbar — prüfe ~/.nanobot/config.json"})}
            return

        session_key = f"chat:{conv_id_str}"
        logger.info("Nanobot-Run gestartet, session=%s, prompt_len=%d", session_key, len(full_prompt))

        bot_task = asyncio.create_task(bot.run(full_prompt, session_key=session_key))

        try:
            while not bot_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(bot_task), timeout=10.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"ts": int(time.time())})}

            bot_result = bot_task.result()
            content = bot_result.content or ""
            logger.info("Nanobot-Antwort erhalten, Länge=%d", len(content))
        except Exception as e:
            logger.exception("Nanobot-Fehler in Konversation %s", conv_id_str)
            yield {"event": "error", "data": json.dumps({"error": f"Nanobot-Fehler: {e}"})}
            return

        async with async_session() as save_db:
            assistant_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content=content,
            )
            save_db.add(assistant_msg)
            await save_db.commit()

        yield {"event": "done", "data": json.dumps({
            "message_id": str(assistant_msg.id),
            "tokens": 0,
            "content": content,
        })}

    return EventSourceResponse(generate())
