"""Triage-Service: Pollt automatisch neue E-Mails (120s) und Teams-Chats (300s).

Läuft als Hintergrund-Tasks beim Backend-Start. Jede neue E-Mail wird als
AgentJob(job_type="email_triage") in die Queue geschrieben, jede neue
Chat-Nachricht als AgentJob(job_type="chat_triage"). Nanobot empfängt die
Jobs via Bridge (pg_notify → WebSocket) und verarbeitet sie.

E-Mail-Triage:
  1. E-Mail lesen → LLM-Klassifikation → Aktion (Draft / Task / FYI)

Chat-Triage:
  1. Chat-Nachricht lesen → LLM-Klassifikation → Aktion (Task / FYI)
  2. Meeting-Transkript-Benachrichtigungen erkennen → AgentJob(meeting_summary)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

from dateutil.parser import isoparse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session
from app.models import AgentJob, ChatTriage, EmailTriage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("taskpilot.triage")

MAX_EMAILS_PER_CYCLE = 20


def _get_graph_client() -> GraphClient | None:
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return None
    return GraphClient(GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    ))


async def _get_known_message_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(select(EmailTriage.message_id))
    return {row[0] for row in result.all()}


def _parse_received_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return isoparse(raw)
    except (ValueError, TypeError):
        return None


async def _create_triage_job(db: AsyncSession, email_data: dict) -> None:
    """Erstellt einen EmailTriage-Record und einen AgentJob für eine neue E-Mail.

    Keine Vorab-Klassifikation -- nanobot uebernimmt alles via LLM.
    """
    from app.services.llm_defaults import get_default_local_model

    from_info = email_data.get("from", {}).get("emailAddress", {})
    from_addr = from_info.get("address", "")
    subject = email_data.get("subject", "")
    inference = email_data.get("inferenceClassification", "")

    triage_record = EmailTriage(
        message_id=email_data["id"],
        subject=subject,
        from_address=from_addr,
        from_name=from_info.get("name"),
        received_at=_parse_received_at(email_data.get("receivedDateTime")),
        inference_class=inference,
        triage_class=None,
        confidence=None,
        suggested_action=None,
        status="pending",
    )
    db.add(triage_record)

    local_model = await get_default_local_model(db)

    agent_job = AgentJob(
        task_id=None,
        job_type="email_triage",
        status="queued",
        llm_model=local_model,
        metadata_json={
            "email_message_id": email_data["id"],
            "subject": subject,
            "from_address": from_addr,
            "from_name": from_info.get("name", ""),
            "inference_classification": inference,
            "body_preview": email_data.get("bodyPreview", "")[:500],
            "categories": email_data.get("categories", []),
            "conversation_id": email_data.get("conversationId", ""),
        },
    )
    db.add(agent_job)
    await db.flush()

    triage_record.agent_job_id = agent_job.id


async def _triage_cycle() -> int:
    """Ein Triage-Zyklus: Neue E-Mails erkennen, AgentJobs für nanobot erstellen."""
    client = _get_graph_client()
    if client is None:
        return 0

    processed = 0
    try:
        async with async_session() as db:
            known_ids = await _get_known_message_ids(db)

            data = await client.list_emails(folder="inbox", top=MAX_EMAILS_PER_CYCLE)
            new_emails = [
                msg for msg in data.get("value", [])
                if msg.get("id") and msg["id"] not in known_ids
            ]

            for email_data in new_emails:
                await _create_triage_job(db, email_data)
                processed += 1

            await db.commit()

    except PermissionError as e:
        logger.warning("Graph API Permission-Fehler: %s", e)
    except Exception:
        logger.exception("Triage-Zyklus Fehler")
    finally:
        if client:
            await client.close()

    return processed


async def run_triage_now(top: int = 50) -> int:
    """Manueller Triage-Trigger (für API-Endpoint, optional)."""
    client = _get_graph_client()
    if client is None:
        return 0

    processed = 0
    try:
        async with async_session() as db:
            known_ids = await _get_known_message_ids(db)

            data = await client.list_emails(folder="inbox", top=top)
            new_emails = [
                msg for msg in data.get("value", [])
                if msg.get("id") and msg["id"] not in known_ids
            ]

            for email_data in new_emails:
                await _create_triage_job(db, email_data)
                processed += 1

            await db.commit()
    except Exception:
        logger.exception("Manueller Triage-Lauf Fehler")
    finally:
        if client:
            await client.close()

    return processed


async def triage_loop() -> None:
    """Automatische Endlosschleife: Prueft alle 2 Minuten auf neue E-Mails."""
    settings = get_settings()
    interval = settings.triage_interval_seconds
    logger.info(
        "Triage-Service gestartet -- automatischer Poll alle %d Sekunden",
        interval,
    )
    await asyncio.sleep(5)
    while True:
        try:
            count = await _triage_cycle()
            if count:
                logger.info("Triage: %d neue E-Mail(s) → AgentJobs für nanobot erstellt", count)
        except Exception:
            logger.exception("Triage-Service: unerwarteter Fehler")
        await asyncio.sleep(interval)


MAX_CHAT_MESSAGES_PER_CYCLE = 30


async def _get_known_chat_message_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(select(ChatTriage.message_id))
    return {row[0] for row in result.all()}


async def _create_chat_triage_job(
    db: AsyncSession, chat_id: str, msg: dict, chat_type: str | None = None,
) -> None:
    """Erstellt einen ChatTriage-Record und einen AgentJob für eine neue Chat-Nachricht."""
    from app.services.llm_defaults import get_default_local_model

    sender = (msg.get("from") or {}).get("user", {})
    from_name = sender.get("displayName", "")
    from_id = sender.get("id", "")
    body = (msg.get("body") or {}).get("content", "")[:500]

    triage_record = ChatTriage(
        chat_id=chat_id,
        message_id=msg["id"],
        from_name=from_name,
        from_id=from_id,
        body_preview=body,
        chat_type=chat_type,
        received_at=_parse_received_at(msg.get("createdDateTime")),
        triage_class=None,
        confidence=None,
        suggested_action=None,
        status="pending",
    )
    db.add(triage_record)

    local_model = await get_default_local_model(db)

    agent_job = AgentJob(
        task_id=None,
        job_type="chat_triage",
        status="queued",
        llm_model=local_model,
        metadata_json={
            "chat_id": chat_id,
            "chat_message_id": msg["id"],
            "from_name": from_name,
            "from_id": from_id,
            "body_preview": body,
            "chat_type": chat_type or "",
            "created_at": msg.get("createdDateTime", ""),
        },
    )
    db.add(agent_job)
    await db.flush()

    triage_record.agent_job_id = agent_job.id


async def _chat_triage_cycle() -> int:
    """Ein Chat-Triage-Zyklus: Neue Teams-Nachrichten erkennen, AgentJobs erstellen."""
    client = _get_graph_client()
    if client is None:
        return 0

    processed = 0
    try:
        async with async_session() as db:
            known_ids = await _get_known_chat_message_ids(db)

            chats = await client.list_chats(top=20)
            for chat in chats:
                chat_id = chat.get("id")
                if not chat_id:
                    continue
                chat_type = chat.get("chatType")

                try:
                    msgs = await client.list_chat_messages(chat_id=chat_id, top=10)
                except Exception:
                    logger.warning("Chat-Nachrichten für %s nicht ladbar", chat_id[:20])
                    continue

                for msg in msgs:
                    msg_id = msg.get("id")
                    msg_type = msg.get("messageType")
                    if not msg_id or msg_id in known_ids:
                        continue
                    if msg_type in ("systemEventMessage",):
                        continue
                    await _create_chat_triage_job(db, chat_id, msg, chat_type)
                    processed += 1

            await db.commit()

    except PermissionError as e:
        logger.warning("Graph API Permission-Fehler (Chat): %s", e)
    except Exception:
        logger.exception("Chat-Triage-Zyklus Fehler")
    finally:
        if client:
            await client.close()

    return processed


async def chat_triage_loop() -> None:
    """Automatische Endlosschleife: Prüft alle 5 Minuten auf neue Chat-Nachrichten."""
    settings = get_settings()
    interval = settings.chat_triage_interval_seconds
    logger.info(
        "Chat-Triage-Service gestartet -- automatischer Poll alle %d Sekunden",
        interval,
    )
    await asyncio.sleep(15)
    while True:
        try:
            count = await _chat_triage_cycle()
            if count:
                logger.info("Chat-Triage: %d neue Nachricht(en) → AgentJobs erstellt", count)
        except Exception:
            logger.exception("Chat-Triage-Service: unerwarteter Fehler")
        await asyncio.sleep(interval)


_triage_task: asyncio.Task | None = None
_chat_triage_task: asyncio.Task | None = None


async def start_triage_service() -> None:
    global _triage_task, _chat_triage_task
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        logger.info("Triage-Service deaktiviert (Graph API nicht konfiguriert)")
        return
    _triage_task = asyncio.create_task(triage_loop())
    _chat_triage_task = asyncio.create_task(chat_triage_loop())
    logger.info("Triage-Service: E-Mail (120s) + Chat (300s) Hintergrund-Tasks laufen")


async def stop_triage_service() -> None:
    global _triage_task, _chat_triage_task
    for task in (_triage_task, _chat_triage_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _triage_task = None
    _chat_triage_task = None
