"""Inbox-Triage-Service: Pollt automatisch neue E-Mails und erstellt AgentJobs für nanobot.

Läuft als Hintergrund-Task beim Backend-Start (alle 2 Min). Kein manuelles
Anstossen nötig. Jede neue E-Mail wird als AgentJob(job_type="email_triage")
in die Queue geschrieben. Nanobot empfängt den Job via Bridge (pg_notify →
WebSocket) und führt die komplette Verarbeitung durch:

1. E-Mail lesen (get_email + get_email_categories)
2. LLM-Klassifikation (via LiteLLM → Ollama lokal)
3. Outlook-Kategorie setzen (set_email_categories)
4. Aktion ausführen (create_draft / create_task / move_email_to_folder)
5. AgentJob-Status aktualisieren

Kein Fallback, keine regelbasierte Klassifikation. Wenn nanobot nicht läuft,
bleiben die Jobs in der Queue bis er wieder verfügbar ist.
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
from app.models import AgentJob, EmailTriage

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

    agent_job = AgentJob(
        task_id=None,
        job_type="email_triage",
        status="queued",
        llm_model="ollama/qwen3.5:35b",
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


_triage_task: asyncio.Task | None = None


async def start_triage_service() -> None:
    global _triage_task
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        logger.info("Triage-Service deaktiviert (Graph API nicht konfiguriert)")
        return
    _triage_task = asyncio.create_task(triage_loop())
    logger.info("Triage-Service: Automatischer Hintergrund-Task laeuft")


async def stop_triage_service() -> None:
    global _triage_task
    if _triage_task and not _triage_task.done():
        _triage_task.cancel()
        try:
            await _triage_task
        except asyncio.CancelledError:
            pass
    _triage_task = None
