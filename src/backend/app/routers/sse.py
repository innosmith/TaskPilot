import asyncio

import asyncpg
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import get_user_from_token_light
from app.config import get_settings
from app.models import User

router = APIRouter(prefix="/api/sse", tags=["sse"])


async def _listen_pg(channels: list[str]):
    settings = get_settings()
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )
    queue: asyncio.Queue = asyncio.Queue()

    def _callback(conn, pid, channel, payload):
        queue.put_nowait({"channel": channel, "data": payload})

    for ch in channels:
        await conn.add_listener(ch, _callback)

    try:
        while True:
            msg = await queue.get()
            yield msg
    finally:
        for ch in channels:
            await conn.remove_listener(ch, _callback)
        await conn.close()


@router.get("/events")
async def event_stream(_user: User = Depends(get_user_from_token_light)):
    async def generate():
        async for msg in _listen_pg(["tasks_changed", "agent_jobs_changed", "email_triage_changed", "chat_triage_changed"]):
            yield {
                "event": msg["channel"],
                "data": msg["data"],
            }

    return EventSourceResponse(generate())
