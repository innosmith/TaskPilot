"""Router für LLM-Chat-Konversationen mit Streaming via litellm."""

import asyncio
import json
import logging
import os
import pathlib
import threading
import time
import uuid

import litellm
import markdown as md_lib
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import get_current_user, require_role
from app.config import get_settings
from app.database import get_db, async_session
from app.models import AgentJob, BoardColumn, Project, Task, User
from app.models.models import LlmConversation, LlmMessage

litellm.drop_params = True

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

# Hinweis fuer den reinen Chat-Modus (kein Tool-/MCP-Zugriff). Verhindert, dass das
# Modell eine Live-Datensuche (z. B. SIGNA-Signale) vortaeuscht oder ins Leere laufen
# laesst, wenn der Nutzer versehentlich nicht im Agent-Modus ist.
_PLAIN_CHAT_TOOL_HINT = (
    "Du bist im reinen Chat-Modus und hast in diesem Modus KEINEN Zugriff auf Live-Tools "
    "oder Firmendaten (SIGNA-Signale/Recherche, E-Mail, Kalender, CRM/Pipedrive, "
    "Buchhaltung/Bexio, Aufgaben). Wenn der Nutzer nach solchen Live-Daten fragt – "
    "insbesondere nach einer SIGNA-Signal- oder semantischen Recherche – fuehre KEINE "
    "erfundene Suche durch. Weise stattdessen kurz und freundlich darauf hin, dass dafuer "
    "der Agent-Modus (InnoPilot) noetig ist, und bitte den Nutzer, oben links auf 'Agent' "
    "umzuschalten und die Anfrage dort erneut zu stellen. Allgemeine Wissensfragen "
    "beantwortest du normal. Sprache: Schweizer Hochdeutsch (ss statt ß, korrekte Umlaute)."
)


def _should_enable_thinking(model_id: str) -> bool:
    """Prüft via LiteLLM-Library ob ein Modell Reasoning/Thinking unterstützt."""
    try:
        return litellm.supports_reasoning(model=model_id)
    except Exception:
        return False


# ── Datei-Anhänge als LLM-Kontext (Dokumenten-Kontext-Brücke) ──

_UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"
_CHAT_UPLOAD_SUBFOLDER = "chat"
_CHAT_UPLOAD_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
# Erlaubte Endungen für Chat-Kontext-Dateien (Text + PDF/DOCX/XLSX). Bilder
# laufen über einen separaten Vision-Pfad und sind hier bewusst ausgeschlossen.
_CHAT_UPLOAD_ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css", ".sql", ".sh",
    ".log", ".ini", ".toml", ".cfg", ".conf",
    ".pdf", ".docx", ".xlsx",
}


@router.post("/uploads")
async def upload_chat_context_file(
    file: UploadFile,
    _user: User = Depends(require_role("owner")),
):
    """Lädt eine Datei als Chat-/Agent-Kontext hoch (mit ClamAV-Scan).

    Liefert eine `upload_id` zurück, die als `local_upload`-Kontextquelle an die
    Chat-/Agent-Endpoints übergeben werden kann. Der Inhalt wird beim Senden
    serverseitig via `context_resolver` extrahiert.
    """
    from app.routers.uploads import _scan_with_clamav

    ext = pathlib.Path(file.filename or "datei").suffix.lower()
    if ext not in _CHAT_UPLOAD_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dateityp '{ext or 'unbekannt'}' wird nicht unterstützt. "
                "Erlaubt: PDF, DOCX, XLSX und Textformate."
            ),
        )

    data = await file.read()
    if len(data) > _CHAT_UPLOAD_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Datei zu gross (max 10 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Leere Datei")

    is_clean = await _scan_with_clamav(data)
    if not is_clean:
        raise HTTPException(status_code=422, detail="Datei wurde als schädlich erkannt")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = _UPLOADS_DIR / _CHAT_UPLOAD_SUBFOLDER / stored_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    return {
        "upload_id": f"{_CHAT_UPLOAD_SUBFOLDER}/{stored_name}",
        "name": file.filename or stored_name,
        "mime_type": file.content_type or "",
    }


async def _resolve_attached_context(context_sources: list | None) -> str:
    """Löst Kontext-Quellen (lokale Uploads + OneDrive) zu einem LLM-Block auf.

    Gemeinsame Brücke für Chat- und Agent-Modus: extrahiert die Inhalte der
    angehängten Dokumente und liefert einen `<attached_files>`-Block. Fehler
    dürfen den Chat/Agent niemals blockieren — im Zweifel leerer String.
    """
    if not context_sources:
        return ""

    from app.services.context_resolver import resolve_context_sources

    needs_graph = any(
        str(s.get("type", "")).startswith("onedrive") for s in context_sources
    )
    graph_client = None
    if needs_graph:
        from app.services.graph import get_graph_client

        graph_client = get_graph_client()
        if graph_client is None:
            logger.warning("Graph nicht konfiguriert — OneDrive-Kontext wird übersprungen")

    try:
        ctx = await resolve_context_sources(context_sources, graph_client)
        return ctx.to_llm_context()
    except Exception:  # noqa: BLE001 - best-effort, darf den Chat nie blockieren
        logger.exception("Kontext-Auflösung der Anhänge fehlgeschlagen")
        return ""


@router.get("/conversations")
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    task_id: uuid.UUID | None = None,
    user: User = Depends(require_role("owner")),
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

    from sqlalchemy import or_
    user_filter = or_(LlmConversation.user_id == user.id, LlmConversation.user_id.is_(None))

    count_q = select(func.count()).select_from(LlmConversation).where(user_filter)
    if task_id:
        count_q = count_q.where(LlmConversation.task_id == task_id)
    total = (await db.execute(count_q)).scalar_one()

    q = (
        select(LlmConversation, msg_count_sq, last_preview_sq)
        .where(user_filter)
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
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Neue Konversation erstellen."""
    from app.services.llm_defaults import get_default_local_model_from_settings

    settings = user.settings or {}
    fallback = get_default_local_model_from_settings(settings)
    default_model = settings.get("llm_default_model") or fallback
    default_temp = settings.get("llm_default_temperature", 0.7)

    conv = LlmConversation(
        title=body.get("title"),
        task_id=body.get("task_id"),
        user_id=user.id,
        model=body.get("model", default_model),
        mode=body.get("mode", "chat"),
        temperature=body.get("temperature", default_temp),
        grounding=body.get("grounding") or {},
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
        "grounding": conv.grounding or {},
        "total_tokens": conv.total_tokens,
        "total_cost_usd": float(conv.total_cost_usd),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.delete("/conversations")
async def delete_all_conversations(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Alle Chat-Konversationen des Users löschen (Nachrichten per ON DELETE CASCADE)."""
    res = await db.execute(
        delete(LlmConversation).where(LlmConversation.user_id == user.id)
    )
    return {"ok": True, "deleted": res.rowcount or 0}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(require_role("owner")),
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
        "grounding": conv.grounding or {},
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
    user: User = Depends(require_role("owner")),
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
    user: User = Depends(require_role("owner")),
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
    if "grounding" in body:
        conv.grounding = body["grounding"] or {}

    await db.flush()
    return {
        "id": str(conv.id),
        "title": conv.title,
        "model": conv.model,
        "mode": conv.mode,
        "temperature": conv.temperature,
        "grounding": conv.grounding or {},
    }


@router.post("/conversations/{conversation_id}/messages/batch")
async def batch_save_messages(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(require_role("owner")),
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
    user: User = Depends(require_role("owner")),
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
    context_sources = body.get("context_sources", [])

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

    # Inhalte angehängter Dokumente serverseitig extrahieren und als Kontext-Block
    # vor die aktuelle Frage stellen (funktioniert auch ohne Tool-Zugriff).
    attached_context = await _resolve_attached_context(context_sources)

    messages_for_llm = [{"role": "system", "content": _PLAIN_CHAT_TOOL_HINT}]
    for msg in conv.messages:
        messages_for_llm.append({"role": msg.role, "content": msg.content})
    if attached_context:
        messages_for_llm.append({
            "role": "user",
            "content": (
                "Die folgenden Dokumente wurden als Kontext angehängt. "
                "Beziehe dich bei deiner Antwort darauf:\n\n" + attached_context
            ),
        })
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
            yield {"event": "error", "data": json.dumps({"error": "Deep Research fehlgeschlagen"})}
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
        if not model.startswith("ollama/"):
            thinking_enabled = _should_enable_thinking(model)
            if thinking_enabled:
                if model.startswith("anthropic/"):
                    extra_params["thinking"] = {"type": "enabled", "budget_tokens": 8192}
                else:
                    extra_params["thinking"] = {"type": "enabled"}

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages_for_llm,
                temperature=temperature if not extra_params.get("thinking") else 1.0,
                stream=True,
                api_base=get_settings().ollama_base_url if model.startswith("ollama/") else None,
                **extra_params,
            )

            _first_delta_logged = False
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta:
                    if not _first_delta_logged:
                        _attrs = {k: v for k, v in vars(delta).items() if v is not None and k != "content"}
                        if _attrs:
                            logger.debug("[Thinking-Debug] model=%s first delta attrs: %s", model, _attrs)
                        _first_delta_logged = True

                    rc = getattr(delta, "reasoning_content", None)
                    if not rc:
                        rc = getattr(delta, "thinking", None)
                    if not rc and hasattr(delta, "thinking_blocks"):
                        blocks = delta.thinking_blocks or []
                        if blocks and isinstance(blocks, list):
                            block = blocks[0]
                            rc = block.get("thinking", "") if isinstance(block, dict) else getattr(block, "thinking", "")

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
                "data": json.dumps({"error": "LLM-Streaming fehlgeschlagen"}),
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
    user: User = Depends(require_role("owner")),
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

# ── Agent-Event-Buffer (Background-Decoupling) ──────────────────
# Jeder laufende/kürzlich beendete Agent-Run hat eine Event-Liste.
# Neue Subscriber bekommen alle Events ab einem Offset.

_agent_events: dict[str, list[dict]] = {}
_agent_conditions: dict[str, asyncio.Condition] = {}
_agent_running: dict[str, bool] = {}
_AGENT_EVENT_TTL = 600  # Events 10min nach Abschluss aufbewahren

# Job-IDs, fuer die der Nutzer einen Stopp angefordert hat. Der Agent-Thread
# prueft dies kooperativ in seinen Callbacks (naechste Tool-/Text-Grenze) und
# bricht dann ab -- ein echter Stopp, nicht nur ein abgeklemmter Client-Stream.
_agent_cancel: set[str] = set()


class _AgentCancelled(Exception):
    """Wird in den Hermes-Callbacks ausgelöst, wenn der Nutzer gestoppt hat."""

# Offene clarify-Rückfragen (HITL): clarify_id -> {event, answer, job_id}.
# Der Agent-Thread blockiert auf ``event`` bis der Nutzer via Endpoint antwortet.
_clarify_pending: dict[str, dict] = {}


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
    """Kompakter Skill-Index (Name + Beschreibung) statt Volltext-Injektion.

    Hermes-nativ lädt der Agent den vollständigen Skill bei Bedarf selbst via
    ``skill_view`` (Progressive Disclosure). Hier liefern wir nur das Inhalts-
    verzeichnis, damit der Prompt schlank bleibt und der Agent weiss, welche
    Skills es gibt.
    """
    from app.services.hermes_config import discover_skills

    skills = discover_skills()
    if not skills:
        return "(Keine Skills hinterlegt.)"

    lines = []
    for s in skills:
        tools = f" [Tools: {', '.join(s['requires_toolsets'])}]" if s["requires_toolsets"] else ""
        lines.append(f"- **{s['name']}**: {s['description']}{tools}")
    lines.append("")
    lines.append("Lade den vollständigen Skill bei Bedarf mit skill_view(name='<name>'), bevor du eine Fachaufgabe ausführst.")
    return "\n".join(lines)


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
            "semantic_search_signals(query) — Signale semantisch nach Thema/Bedeutung suchen; "
            "search_signals(query) — Signale nach Stichwort durchsuchen; "
            "get_briefing(id) — Briefing lesen"
        ),
    },
}


def _get_configured_mcp_servers() -> dict:
    """Liest die MCP-Server-Liste aus der Hermes-Config (~/.hermes/config.yaml)."""
    import yaml
    from app.services.hermes_config import get_hermes_home

    config_path = get_hermes_home() / "config.yaml"
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config.get("mcp_servers", {})
    except Exception:
        return {}


def _build_agent_prompt(
    user_content: str,
    conversation_messages: list,
    attached_context: str = "",
) -> str:
    """Baut einen schlanken Prompt — Tool-Definitionen kommen nativ vom Hermes-Agent via MCP."""
    from datetime import datetime, timezone as tz
    from zoneinfo import ZoneInfo

    skills_text = _load_agent_skills()

    now_zurich = datetime.now(ZoneInfo("Europe/Zurich"))
    date_context = now_zurich.strftime("%A, %d. %B %Y, %H:%M Uhr")
    # Explizite Datums-Anker, damit relative Angaben ("nächste Woche") eindeutig sind.
    from datetime import timedelta as _td
    _days_to_mon = (7 - now_zurich.weekday()) % 7 or 7  # nächster Montag (heute zählt nicht)
    next_monday = (now_zurich + _td(days=_days_to_mon)).date()
    this_monday = (now_zurich - _td(days=now_zurich.weekday())).date()

    # Jeden Wochentag mit effektivem Datum vorrechnen (dynamisch), damit das Modell
    # nicht selbst addieren muss und sich nicht verzählt.
    _wd = ["Mo", "Di", "Mi", "Do", "Fr"]

    def _week_line(monday):
        return ", ".join(
            f"{_wd[i]} {(monday + _td(days=i)).strftime('%d.%m.')}" for i in range(5)
        )

    date_anchors = (
        f"Heute ist {now_zurich.strftime('%A')}, {now_zurich.date().isoformat()}. "
        f"'Diese Woche' (Mo–Fr): {_week_line(this_monday)}. "
        f"'Nächste Woche' (Mo–Fr, beginnt am nächsten Montag): {_week_line(next_monday)}."
    )

    history_lines = []
    for msg in conversation_messages[-10:]:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"**{role_label}:** {msg.content[:500]}")
    history_block = "\n\n".join(history_lines) if history_lines else "(Erste Nachricht)"

    attached_block = ""
    if attached_context:
        attached_block = (
            "\n## Angehängte Dokumente\n\n"
            "Anthony hat folgende Dokumente angehängt. Nutze ihren Inhalt direkt. "
            "Weitere/grössere Dateien kannst du bei Bedarf mit download_file nachladen.\n\n"
            f"{attached_context}\n"
        )

    return f"""Du bist InnoPilot, der KI-Agent von Anthony Smith (InnoSmith GmbH, Schweiz).
Du hast direkten Zugriff auf Firmendaten über deine MCP-Tools (siehst du in deiner Tool-Liste).
Nutze deine Tools aktiv. Behaupte niemals, du hättest keinen Zugriff.

## Aktuell

- Datum/Uhrzeit: {date_context} (Europe/Zurich)
- {date_anchors}
- User: Anthony Smith (du sprichst direkt mit ihm)

## Regeln

- Bei Fragen zu Firmendaten: Sofort passende Tools aufrufen
- Dateien: search_files → download_file
- Buchhaltung: list_accounts, get_journal, list_invoices, search_invoices
- Mehrstufige Aufgaben: Schritt für Schritt, Tool-Ergebnisse auswerten
- Öffentliche/aktuelle Recherche im Internet (News, Studien, Markt, Personen, Firmen): Nutze IMMER `web_search` (und `web_extract` für Detailseiten). Das ist die agentische Web-Recherche.
- WICHTIG — SIGNA ist NICHT das Internet: `semantic_search_signals`/`search_signals` durchsuchen NUR die interne strategische Signal-Datenbank (ISI). Nutze SIGNA ausschliesslich, wenn explizit nach SIGNA-Signalen/Briefings gefragt wird — NICHT für allgemeine Web-Recherche. Bei „recherchiere aktuelle Entwicklungen im Internet" → `web_search`, nicht SIGNA.
- CRM-Suche (Pipedrive): `search_crm` mit EINEM kurzen Begriff (Name, Firma, E-Mail) aufrufen, nicht mit ganzen Themensätzen. item_types im Singular (deal,person,organization).
- Frühere Gespräche: Wenn Anthony sich auf etwas Früheres bezieht ("wie letzte Woche besprochen"), durchsuche den Verlauf mit session_search, bevor du nachfragst.
- Dauerhaftes Wissen: Lernst du eine stabile Präferenz oder Tatsache über Anthony/Arbeitsweise, halte sie knapp mit dem memory-Tool fest.
- Rückfragen bei Mehrdeutigkeit: Ist der Auftrag unklar oder gibt es mehrere sinnvolle Wege, stelle mit dem clarify-Tool eine kurze, strukturierte Rückfrage statt zu raten.
- Grosse Recherche-/Dokument-Aufträge: Zerlege sie bei Bedarf mit delegate_task in Subaufgaben. Externe Ausgaben (E-Mails, Dokumente an Kunden) bleiben IMMER HITL — du lieferst einen Entwurf zur Freigabe, versendest nichts eigenständig.
- Neue Skills: Erstelle Skills mit skill_manage nur als Vorschlag (propose-only). Beschreibe Anthony kurz den Nutzen und überlasse ihm die Freigabe/Aktivierung, statt eigenmächtig viele Skills anzulegen.
- Sprache: Deutsch (Schweizer Hochdeutsch, ss statt ß, korrekte Umlaute ä/ö/ü)
- Zeitzone: IMMER Europe/Zurich — alle Kalenderzeiten sind in dieser Zeitzone
- Kalender: Du verwaltest Anthonys Outlook-Kalender direkt. Bei Terminwünschen IMMER zuerst mit list_calendar_events oder find_free_slots prüfen ob der Slot frei ist, dann mit create_calendar_event buchen. Verweise NICHT auf externe Buchungstools — du bist das Buchungstool.

## Verfügbare Skills (bei Bedarf mit skill_view laden)

{skills_text}
{attached_block}
## Chat-Verlauf

{history_block}

## Anfrage

{user_content}"""


@router.get("/agent-tools")
async def get_agent_tools(user: User = Depends(require_role("owner"))):
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
    user: User = Depends(require_role("owner")),
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
    selected_model = body.get("model", "hermes")
    context_sources = body.get("context_sources", [])
    logger.info("[agent] Nachricht (%.80s…), conv=%s", user_content, conversation_id)

    # Grounding-Politik: Lokale Modelle = voller Zugriff. Cloud-Modelle =
    # Default-Deny; nur explizit freigegebene MCP-Server + optional Memory.
    from app.services.hermes_worker import (
        CLOUD_TOOL_LIMIT,
        _is_local_model,
        count_tools,
        resolve_cloud_toolsets,
    )

    requested_servers = body.get("enabled_servers") or []
    include_memory = bool(body.get("include_memory", False))

    if _is_local_model(selected_model):
        grounding = {"enabled_servers": list(requested_servers), "include_memory": include_memory}
    else:
        valid_servers = resolve_cloud_toolsets(requested_servers)
        tool_count = count_tools(valid_servers) if valid_servers else 0
        if tool_count > CLOUD_TOOL_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Zu viele Tools für ein Cloud-Modell ({tool_count} > {CLOUD_TOOL_LIMIT}). "
                    "Bitte weniger MCP-Server aktivieren."
                ),
            )
        grounding = {"enabled_servers": valid_servers, "include_memory": include_memory}

    conv.grounding = grounding
    # Gewaehltes Modell pro Konversation merken (statt Platzhalter 'hermes'),
    # damit die UI es beim Wiederoeffnen/Reload korrekt wiederherstellen kann.
    conv.model = selected_model

    user_msg = LlmMessage(
        conversation_id=conv.id,
        role="user",
        content=user_content,
    )
    db.add(user_msg)
    await db.flush()

    # Chat-Lernkanal (Saeule 4): "merk dir ..."-Absicht erfassen -> Regel-Vorschlag (HITL).
    try:
        from app.services.learning import extract_teach_intent, record_chat_teach

        lesson = extract_teach_intent(user_content)
        if lesson:
            await record_chat_teach(db, content=lesson, conversation_id=str(conv.id))
    except Exception:  # noqa: BLE001 - best-effort, darf den Chat nie blockieren
        logger.warning("Chat-Teach-Erfassung fehlgeschlagen")

    if not conv.title and len(conv.messages) <= 1:
        conv.title = user_content[:80] + ("..." if len(user_content) > 80 else "")

    # Inhalte angehängter Dokumente extrahieren und in den Agent-Prompt einbetten
    # (zusätzlich zu den On-Demand-Tools search_files/download_file).
    attached_context = await _resolve_attached_context(context_sources)

    sorted_messages = sorted(conv.messages, key=lambda m: m.created_at)
    full_prompt = _build_agent_prompt(user_content, sorted_messages, attached_context)

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
        _run_agent_background(
            job_id_str,
            conv_id_str,
            full_prompt,
            selected_model,
            enabled_servers=grounding["enabled_servers"],
            include_memory=grounding["include_memory"],
        )
    )

    return {
        "job_id": job_id_str,
        "conversation_id": conv_id_str,
        "status": "running",
    }


async def _run_agent_background(
    job_id: str,
    conv_id: str,
    prompt: str,
    model: str,
    *,
    enabled_servers: list[str] | None = None,
    include_memory: bool = False,
):
    """Führt den Hermes-Agent (InnoPilot) als Background-Task aus.

    Hermes ist synchron: ``AIAgent.run_conversation`` läuft in einem Thread
    (``asyncio.to_thread``). Die synchronen Callbacks (Text/Reasoning/Tools)
    feuern aus dem Worker-Thread und werden via ``loop.call_soon_threadsafe``
    threadsicher in eine ``asyncio.Queue`` gebrückt. So bleibt die volle
    Transparenz erhalten: man sieht InnoPilot denken (``thinking``), Tools
    aufrufen (``tool_start``/``tool_event``) und streamen (``chunk``).
    """
    from datetime import datetime, timezone as tz
    from app.services.hermes_worker import build_chat_agent, ensure_runtime_ready

    t_start = time.time()
    loop = asyncio.get_running_loop()

    async def _update_agent_job(
        status: str,
        output: str | None = None,
        error_message: str | None = None,
        tools_used: list[str] | None = None,
        trace: list[dict] | None = None,
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
            if tools_used or trace:
                meta = dict(job.metadata_json or {})
                if tools_used:
                    meta["tools_used"] = tools_used
                # Trace im selben Format wie der Worker, damit der bestehende
                # Trace-Endpoint (metadata_json['trace']) auch Chat-Jobs zeigt.
                if trace:
                    meta["trace"] = trace
                job.metadata_json = meta
            await sdb.commit()

    queue: asyncio.Queue = asyncio.Queue()

    def _emit(evt_type: str, payload):
        """Threadsicher ein Event in die Queue legen (aus dem Agent-Thread)."""
        loop.call_soon_threadsafe(queue.put_nowait, (evt_type, payload))

    def _check_cancel():
        """Kooperativer Abbruch: an Tool-/Text-Grenzen den Stopp-Wunsch prüfen."""
        if job_id in _agent_cancel:
            raise _AgentCancelled()

    # Synchrone Hermes-Callbacks -> Queue-Brücke
    def on_text(text: str):
        _check_cancel()
        if text:
            _emit("chunk", text)

    # Trace-Akkumulator: gleiches Format wie der Worker (thinking/tool_start/
    # tool_complete), damit der bestehende Trace-Endpoint Chat-Jobs anzeigt.
    _trace: list[dict] = []
    _MAX_TRACE = 200

    def _trace_append(event: dict):
        if len(_trace) < _MAX_TRACE:
            _trace.append(event)

    def on_reasoning(text: str):
        _check_cancel()
        if text:
            _trace_append({"type": "thinking", "text": str(text)[:2000]})
            _emit("thinking", text)

    _tools_used: list[str] = []

    def on_tool_start(tc_id, name, args):
        _check_cancel()
        if name and name not in _tools_used:
            _tools_used.append(str(name))
        event = {"type": "tool_start", "name": str(name)}
        # Bei Skill-Aufrufen den geladenen Skill-Namen miterfassen -- analog zum
        # Worker (_on_tool_start), damit die Skill-Nutzungs-Analytics auch
        # explizite skill_view-Loads aus dem Chat zaehlen kann.
        if str(name) in ("skill_view", "skill_manage"):
            skill = None
            try:
                if isinstance(args, dict):
                    skill = args.get("name") or args.get("skill")
                elif isinstance(args, str) and args.strip().startswith("{"):
                    skill = (json.loads(args) or {}).get("name")
            except Exception:  # noqa: BLE001 - Trace darf nie scheitern
                skill = None
            if skill:
                event["skill"] = str(skill)
        _trace_append(event)
        _emit("tool_start", str(name))

    def on_tool_complete(tc_id, name, args, result):
        _trace_append({"type": "tool_complete", "name": str(name), "result": str(result)[:500]})
        _emit("tool_event", json.dumps(
            {"tool": str(name), "result": str(result)[:500]}, ensure_ascii=False
        ))
        _check_cancel()

    def clarify_callback(question: str, choices) -> str:
        """HITL-Rückfrage: blockiert den Agent-Thread bis der Nutzer antwortet.

        Läuft im Hermes-Worker-Thread. Wir emittieren ein clarify-SSE-Event und
        warten auf die Antwort (gesetzt über den /agent/clarify-Endpoint). Bei
        Timeout gibt der Callback einen neutralen Hinweis zurück, damit der Agent
        eigenständig eine sinnvolle Annahme treffen und fortfahren kann.
        """
        clarify_id = uuid.uuid4().hex
        ev = threading.Event()
        _clarify_pending[clarify_id] = {"event": ev, "answer": None, "job_id": job_id}
        try:
            choice_list = [str(c) for c in choices] if isinstance(choices, (list, tuple)) else []
            _emit("clarify", json.dumps({
                "clarify_id": clarify_id,
                "question": str(question),
                "choices": choice_list,
            }, ensure_ascii=False))
            answered = ev.wait(timeout=MAX_AGENT_TIMEOUT)
            if not answered:
                return "Keine Antwort des Nutzers erhalten. Triff eine sinnvolle Annahme und fahre fort."
            return _clarify_pending.get(clarify_id, {}).get("answer") or "(leere Antwort)"
        finally:
            _clarify_pending.pop(clarify_id, None)

    await _push_agent_event(job_id, {"event": "status", "data": json.dumps({"content": "InnoPilot wird initialisiert..."})})

    if not await ensure_runtime_ready():
        logger.error("[agent-bg] Hermes-Runtime nicht verfügbar")
        await _update_agent_job("failed", error_message="Hermes-Runtime nicht verfügbar")
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": "InnoPilot nicht verfügbar — prüfe ~/.hermes/config.yaml"})})
        _agent_running[job_id] = False
        asyncio.create_task(_cleanup_agent_events(job_id))
        return

    try:
        agent = await asyncio.to_thread(
            build_chat_agent,
            model,
            enabled_servers=enabled_servers,
            include_memory=include_memory,
            on_text=on_text,
            on_reasoning=on_reasoning,
            on_tool_start=on_tool_start,
            on_tool_complete=on_tool_complete,
            clarify_callback=clarify_callback,
            session_id=f"chat-{conv_id}",
        )
    except Exception:
        logger.exception("[agent-bg] Agent-Init fehlgeschlagen")
        await _update_agent_job("failed", error_message="Agent-Initialisierung fehlgeschlagen")
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": "InnoPilot konnte nicht initialisiert werden"})})
        _agent_running[job_id] = False
        asyncio.create_task(_cleanup_agent_events(job_id))
        return

    active_model = getattr(agent, "model", "?")
    await _push_agent_event(job_id, {"event": "status", "data": json.dumps(
        {"content": f"InnoPilot bereit (Modell: {active_model}) — Aufgabe wird verarbeitet..."})})
    logger.info("[agent-bg] Run gestartet, conv=%s, model=%s, prompt_len=%d",
                conv_id, active_model, len(prompt))

    def _run_sync() -> str:
        result = agent.run_conversation(prompt)
        if isinstance(result, dict):
            return str(result.get("final_response") or "")
        return str(result or "")

    bot_task = asyncio.create_task(asyncio.to_thread(_run_sync))
    # Bei vorzeitigem Return (Stopp/Timeout) eine evtl. Thread-Exception abgreifen,
    # damit kein "Task exception was never retrieved" geloggt wird.
    bot_task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    async def _drain(evt_type: str, evt_data):
        if evt_type == "chunk":
            await _push_agent_event(job_id, {"event": "chunk", "data": json.dumps({"content": evt_data})})
        elif evt_type == "thinking":
            await _push_agent_event(job_id, {"event": "thinking", "data": json.dumps({"content": evt_data})})
        elif evt_type == "tool_start":
            await _push_agent_event(job_id, {"event": "tool_start", "data": json.dumps({"tools": evt_data})})
        elif evt_type == "tool_event":
            await _push_agent_event(job_id, {"event": "tool_event", "data": evt_data})
        elif evt_type == "clarify":
            await _push_agent_event(job_id, {"event": "clarify", "data": evt_data})
        elif evt_type == "status":
            await _push_agent_event(job_id, {"event": "status", "data": json.dumps({"content": evt_data})})

    try:
        while not bot_task.done():
            # Stopp-Wunsch des Nutzers: Client sofort entkoppeln, Thread läuft
            # kooperativ aus (Callback-Abbruch an nächster Grenze).
            if job_id in _agent_cancel:
                logger.info("[agent-bg] Stopp durch Nutzer, job=%s", job_id)
                await _update_agent_job("failed", error_message="Vom Benutzer gestoppt", tools_used=list(_tools_used), trace=list(_trace))
                await _push_agent_event(job_id, {"event": "stopped", "data": json.dumps({"content": "Vom Benutzer gestoppt"})})
                _agent_running[job_id] = False
                _agent_cancel.discard(job_id)
                # clarify ggf. entsperren, damit der Thread nicht hängen bleibt
                for cid, p in list(_clarify_pending.items()):
                    if p.get("job_id") == job_id:
                        p["answer"] = "Abgebrochen."
                        p["event"].set()
                asyncio.create_task(_cleanup_agent_events(job_id))
                return
            try:
                evt_type, evt_data = await asyncio.wait_for(queue.get(), timeout=2.0)
                await _drain(evt_type, evt_data)
            except asyncio.TimeoutError:
                elapsed = time.time() - t_start
                if elapsed > MAX_AGENT_TIMEOUT:
                    bot_task.cancel()
                    logger.warning("[agent-bg] Timeout nach %.0fs, job=%s", elapsed, job_id)
                    await _update_agent_job("failed", error_message=f"Timeout nach {MAX_AGENT_TIMEOUT}s", tools_used=list(_tools_used), trace=list(_trace))
                    await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": f"InnoPilot hat das Zeitlimit überschritten ({MAX_AGENT_TIMEOUT}s)"})})
                    _agent_running[job_id] = False
                    asyncio.create_task(_cleanup_agent_events(job_id))
                    return

        while not queue.empty():
            evt_type, evt_data = queue.get_nowait()
            await _drain(evt_type, evt_data)

        content = bot_task.result()
        tools_used = list(_tools_used)
        elapsed = time.time() - t_start
        logger.info("[agent-bg] Fertig in %.1fs, Antwort=%d Zeichen, Tools=%s, job=%s",
                    elapsed, len(content), tools_used, job_id)

    except Exception:
        logger.exception("[agent-bg] Fehler in job=%s", job_id)
        await _update_agent_job("failed", error_message="Agent-Ausführung fehlgeschlagen", tools_used=list(_tools_used), trace=list(_trace))
        await _push_agent_event(job_id, {"event": "error", "data": json.dumps({"error": "InnoPilot-Ausführung fehlgeschlagen"})})
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

    await _update_agent_job("completed", output=content, tools_used=tools_used, trace=list(_trace))

    await _push_agent_event(job_id, {"event": "done", "data": json.dumps({
        "message_id": str(assistant_msg.id),
        "tokens": 0,
        "content": content,
        "tools_used": tools_used,
        "elapsed_s": round(time.time() - t_start, 1),
    })})

    _agent_running[job_id] = False
    asyncio.create_task(_cleanup_agent_events(job_id))


@router.post("/conversations/{conversation_id}/agent/clarify")
async def answer_agent_clarify(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(require_role("owner")),
):
    """Antwort auf eine clarify-Rückfrage des Agenten entgegennehmen.

    Setzt die Antwort und entsperrt den blockierten Agent-Thread (siehe
    ``clarify_callback`` in ``_run_agent_background``).
    """
    clarify_id = body.get("clarify_id")
    answer = body.get("answer", "")
    pending = _clarify_pending.get(clarify_id) if clarify_id else None
    if not pending:
        raise HTTPException(status_code=404, detail="Rückfrage nicht gefunden oder bereits abgelaufen")
    pending["answer"] = str(answer)
    pending["event"].set()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/agent/cancel")
async def cancel_agent_run(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(require_role("owner")),
):
    """Laufenden Chat-Agent-Job stoppen (echter, kooperativer Abbruch).

    Setzt den Stopp-Wunsch; der Background-Run entkoppelt den Client sofort und
    der Hermes-Thread bricht an der nächsten Tool-/Text-Grenze ab. Im Gegensatz
    zum reinen Schliessen des Streams läuft der Job danach nicht unbemerkt weiter.
    """
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id fehlt")
    _agent_cancel.add(str(job_id))
    # Falls der Agent gerade auf eine clarify-Antwort wartet: entsperren.
    for cid, p in list(_clarify_pending.items()):
        if p.get("job_id") == str(job_id):
            p["answer"] = "Abgebrochen."
            p["event"].set()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/agent-stream")
async def stream_agent_events(
    conversation_id: uuid.UUID,
    job_id: str = Query(..., description="Agent-Job-ID aus POST-Antwort"),
    offset: int = Query(0, ge=0, description="Event-Offset für Reconnect"),
    user: User = Depends(require_role("owner")),
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
