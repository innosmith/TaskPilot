import asyncio
import json
import logging

import asyncpg
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)

_ws_connection: websockets.ClientConnection | None = None
_bridge_task: asyncio.Task | None = None
_job_queue: asyncio.Queue[str] = asyncio.Queue()


async def _get_ws() -> websockets.ClientConnection | None:
    global _ws_connection
    settings = get_settings()
    try:
        if _ws_connection is None or _ws_connection.close_code is not None:
            url = settings.nanobot_ws_url
            if settings.nanobot_ws_token:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}token={settings.nanobot_ws_token}"
            _ws_connection = await websockets.connect(
                url,
                open_timeout=5,
            )
        return _ws_connection
    except Exception as e:
        logger.warning("nanobot WebSocket nicht erreichbar: %s", e)
        _ws_connection = None
        return None


async def send_job_to_nanobot(job_data: dict) -> bool:
    ws = await _get_ws()
    if ws is None:
        return False
    try:
        await ws.send(json.dumps(job_data))
        logger.info("Job %s an nanobot gesendet", job_data.get("job_id"))
        return True
    except Exception as e:
        logger.warning("Fehler beim Senden an nanobot: %s", e)
        return False


async def _process_queue(query_conn: asyncpg.Connection):
    """Verarbeitet Jobs sequentiell aus der Queue (eine separate Connection fuer Queries)."""
    while True:
        job_id = await _job_queue.get()
        try:
            row = await query_conn.fetchrow(
                """
                SELECT aj.id, aj.task_id, aj.job_type, aj.llm_model,
                       aj.status, aj.metadata,
                       t.title, t.description
                FROM agent_jobs aj
                LEFT JOIN tasks t ON t.id = aj.task_id
                WHERE aj.id = $1 AND aj.status = 'queued'
                """,
                job_id,
            )
            if row is None:
                continue

            metadata = row["metadata"] or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            msg = {
                "type": "agent_job",
                "job_id": str(row["id"]),
                "job_type": row["job_type"] or "generic",
                "task_id": str(row["task_id"]) if row["task_id"] else None,
                "title": row["title"] or "",
                "description": row["description"] or "",
                "llm_override": row["llm_model"],
                "metadata": metadata,
            }
            await send_job_to_nanobot(msg)
        except Exception as e:
            logger.error("Bridge Job-Verarbeitung Fehler fuer %s: %s", job_id, e)
        finally:
            _job_queue.task_done()


async def _listen_and_forward():
    """Lauscht auf PostgreSQL NOTIFY agent_jobs_changed und leitet neue Jobs an nanobot weiter."""
    settings = get_settings()

    listen_conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )

    query_conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )

    logger.info("nanobot-Bridge: Lausche auf agent_jobs_changed")

    processor = asyncio.create_task(_process_queue(query_conn))

    pending = await query_conn.fetch(
        "SELECT id FROM agent_jobs WHERE status = 'queued' ORDER BY created_at"
    )
    if pending:
        logger.info("nanobot-Bridge: %d wartende Jobs gefunden, werden nachgeholt", len(pending))
        for row in pending:
            _job_queue.put_nowait(row["id"])

    def _callback(conn, pid, channel, payload):
        try:
            data = json.loads(payload)
            if data.get("op") != "INSERT":
                return
            job_id = data.get("id")
            if job_id:
                _job_queue.put_nowait(job_id)
        except Exception as e:
            logger.error("Bridge-Callback Parse-Fehler: %s", e)

    await listen_conn.add_listener("agent_jobs_changed", _callback)

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        processor.cancel()
        await listen_conn.remove_listener("agent_jobs_changed", _callback)
        await listen_conn.close()
        await query_conn.close()


async def start_bridge():
    global _bridge_task
    _bridge_task = asyncio.create_task(_listen_and_forward())
    logger.info("nanobot-Bridge gestartet")


async def stop_bridge():
    global _bridge_task, _ws_connection
    if _bridge_task:
        _bridge_task.cancel()
        try:
            await _bridge_task
        except asyncio.CancelledError:
            pass
    if _ws_connection:
        await _ws_connection.close()
        _ws_connection = None
    logger.info("nanobot-Bridge gestoppt")
