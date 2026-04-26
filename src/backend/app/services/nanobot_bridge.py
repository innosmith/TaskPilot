import asyncio
import json
import logging

import asyncpg
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)

_ws_connection: websockets.ClientConnection | None = None
_bridge_task: asyncio.Task | None = None


async def _get_ws() -> websockets.ClientConnection | None:
    global _ws_connection
    settings = get_settings()
    try:
        if _ws_connection is None or _ws_connection.close_code is not None:
            _ws_connection = await websockets.connect(
                settings.nanobot_ws_url,
                additional_headers={"Authorization": f"Bearer {settings.nanobot_ws_token}"},
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


async def _listen_and_forward():
    """Lauscht auf PostgreSQL NOTIFY agent_jobs_changed und leitet neue Jobs an nanobot weiter."""
    settings = get_settings()
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )
    logger.info("nanobot-Bridge: Lausche auf agent_jobs_changed")

    async def _callback(conn, pid, channel, payload):
        try:
            data = json.loads(payload)
            if data.get("op") != "INSERT":
                return

            job_id = data.get("id")
            if not job_id:
                return

            row = await conn.fetchrow(
                """
                SELECT aj.id, aj.task_id, aj.llm_model, aj.status,
                       t.title, t.description
                FROM agent_jobs aj
                JOIN tasks t ON t.id = aj.task_id
                WHERE aj.id = $1 AND aj.status = 'queued'
                """,
                job_id,
            )
            if row is None:
                return

            msg = {
                "type": "agent_job",
                "job_id": str(row["id"]),
                "task_id": str(row["task_id"]),
                "title": row["title"],
                "description": row["description"] or "",
                "llm_override": row["llm_model"],
            }
            await send_job_to_nanobot(msg)
        except Exception as e:
            logger.error("Bridge-Callback Fehler: %s", e)

    await conn.add_listener("agent_jobs_changed", _callback)

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await conn.remove_listener("agent_jobs_changed", _callback)
        await conn.close()


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
