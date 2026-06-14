"""Agent-Scheduler: gibt zeitgesteuerte Agent-Aufträge frei.

Eine dem Agenten zugewiesene Task erzeugt einen Job im Status ``planned``
(siehe ``routers/tasks.py``). Dieser Scheduler hebt ihn am Fälligkeitstag
(``Task.due_date``) auf ``queued`` -- erst dann greift der Hermes-Worker.

Bewusste Entscheidungen:
- **Kein neues Attribut**: der Auslöser ist das bestehende ``due_date`` (Datum).
  Da es keine Uhrzeit trägt, wird am Fälligkeitstag ab einer festen lokalen
  Zeit (``RELEASE_HOUR``) freigegeben; überfällige Jobs sofort.
- **L0 (Block)** wird nie automatisch freigegeben -- der Job bleibt ``planned``.
- Die Steuerungs-Felder (Autonomie/LLM/Datenklasse) werden beim Freigeben aus
  der aktuellen Task übernommen, damit zwischenzeitliche Konfiguration greift.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import AgentJob, Task

logger = logging.getLogger("taskpilot.agent_scheduler")

CHECK_INTERVAL_SECONDS = 300  # 5 Minuten
RELEASE_HOUR = 7  # ab 07:00 lokaler Zeit am Fälligkeitstag
_TZ = ZoneInfo("Europe/Zurich")


async def _release_due_jobs(db: AsyncSession) -> int:
    """Gibt fällige ``planned``-Jobs frei (planned -> queued). Anzahl freigegeben."""
    now_local = datetime.now(_TZ)
    today = now_local.date()

    result = await db.execute(
        select(AgentJob, Task)
        .join(Task, AgentJob.task_id == Task.id)
        .where(
            AgentJob.status == "planned",
            Task.due_date.isnot(None),
            Task.due_date <= today,
        )
    )

    released = 0
    for job, task in result.all():
        # Am Fälligkeitstag erst ab RELEASE_HOUR; überfällige (due < heute) sofort.
        if task.due_date == today and now_local.hour < RELEASE_HOUR:
            continue
        # L0 = Block: bleibt geplant, wird nie automatisch ausgeführt.
        if task.autonomy_level == "L0":
            continue

        meta = dict(job.metadata_json or {})
        meta["autonomy_level"] = task.autonomy_level
        meta["data_class"] = task.data_class
        meta["llm_override"] = task.llm_override
        meta["scheduled_release"] = now_local.isoformat()
        job.metadata_json = meta
        job.llm_model = task.llm_override
        job.status = "queued"
        released += 1
        logger.info(
            "Agent-Job %s freigegeben (Task %s, due=%s) -> queued",
            job.id, task.id, task.due_date,
        )

    return released


async def agent_scheduler_loop() -> None:
    """Endlosschleife: gibt periodisch fällige geplante Agent-Aufträge frei."""
    logger.info("Agent-Scheduler gestartet (Intervall: %ds, Release ab %02d:00)",
                CHECK_INTERVAL_SECONDS, RELEASE_HOUR)
    while True:
        try:
            async with async_session() as db:
                count = await _release_due_jobs(db)
                await db.commit()
                if count:
                    logger.info("%d geplante(r) Agent-Auftrag/Aufträge freigegeben", count)
        except Exception:
            logger.exception("Agent-Scheduler: unerwarteter Fehler")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


_scheduler_task: asyncio.Task | None = None


async def start_agent_scheduler() -> None:
    global _scheduler_task
    _scheduler_task = asyncio.create_task(agent_scheduler_loop())


async def stop_agent_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
