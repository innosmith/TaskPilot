"""Recurring-Task-Scheduler: prüft periodisch, ob neue Task-Instanzen
aus Vorlagen (Templates) erzeugt werden müssen.

Ein Template ist ein Task mit `recurrence_rule IS NOT NULL` und
`template_id IS NULL`.  Instanzen sind Tasks mit gesetztem `template_id`.
"""

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session
from app.models import ChecklistItem, Tag, Task, TaskTag

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("taskpilot.recurring")

CHECK_INTERVAL_SECONDS = 300  # 5 Minuten


async def _get_templates(db: AsyncSession) -> list[Task]:
    result = await db.execute(
        select(Task).where(
            and_(
                Task.recurrence_rule.isnot(None),
                Task.recurrence_rule != "",
                Task.template_id.is_(None),
            )
        )
    )
    return list(result.scalars().all())


async def _latest_instance_time(
    db: AsyncSession, template_id: uuid.UUID
) -> datetime | None:
    result = await db.execute(
        select(func.max(Task.created_at)).where(Task.template_id == template_id)
    )
    return result.scalar_one_or_none()


async def _has_active_instance(db: AsyncSession, template_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(func.count()).where(
            and_(
                Task.template_id == template_id,
                Task.is_completed.is_(False),
            )
        )
    )
    return (result.scalar_one() or 0) > 0


async def _copy_template(db: AsyncSession, template: Task) -> Task:
    """Erzeugt eine frische Instanz aus dem Template inkl. Checkliste + Tags."""
    instance = Task(
        title=template.title,
        description=template.description,
        project_id=template.project_id,
        board_column_id=template.board_column_id,
        board_position=0.0,
        pipeline_column_id=template.pipeline_column_id,
        pipeline_position=None,
        assignee=template.assignee,
        data_class=template.data_class,
        llm_override=template.llm_override,
        autonomy_level=template.autonomy_level,
        template_id=template.id,
    )

    max_pos_result = await db.execute(
        select(func.coalesce(func.max(Task.board_position), 0.0)).where(
            Task.board_column_id == template.board_column_id
        )
    )
    instance.board_position = (max_pos_result.scalar_one() or 0.0) + 1.0

    if template.pipeline_column_id:
        max_pp = await db.execute(
            select(func.coalesce(func.max(Task.pipeline_position), 0.0)).where(
                Task.pipeline_column_id == template.pipeline_column_id
            )
        )
        instance.pipeline_position = (max_pp.scalar_one() or 0.0) + 1.0

    db.add(instance)
    await db.flush()

    cl_result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.task_id == template.id)
        .order_by(ChecklistItem.position)
    )
    for item in cl_result.scalars().all():
        new_item = ChecklistItem(
            task_id=instance.id,
            text=item.text,
            is_checked=False,
            position=item.position,
        )
        db.add(new_item)

    tag_result = await db.execute(
        select(Tag).join(TaskTag).where(TaskTag.task_id == template.id)
    )
    for tag in tag_result.scalars().all():
        db.add(TaskTag(task_id=instance.id, tag_id=tag.id))

    await _create_calendar_blocker(instance, template)

    return instance


async def _create_calendar_blocker(instance: Task, template: Task) -> None:
    """Kalender-Zeitblocker fuer eine Recurring-Task-Instanz erstellen."""
    duration = template.calendar_duration_minutes
    if not duration or duration <= 0:
        return

    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return

    client = GraphClient(GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    ))

    try:
        now = datetime.now(timezone.utc)
        target_date = instance.due_date or now.date()

        preferred = template.calendar_preferred_time or "morning_after_1030"
        if preferred == "morning_after_1030":
            search_start = datetime.combine(target_date, datetime.min.time()).replace(hour=10, minute=30, tzinfo=timezone.utc)
            search_end = datetime.combine(target_date, datetime.min.time()).replace(hour=13, minute=0, tzinfo=timezone.utc)
        elif preferred == "afternoon":
            search_start = datetime.combine(target_date, datetime.min.time()).replace(hour=13, minute=0, tzinfo=timezone.utc)
            search_end = datetime.combine(target_date, datetime.min.time()).replace(hour=18, minute=0, tzinfo=timezone.utc)
        else:
            search_start = datetime.combine(target_date, datetime.min.time()).replace(hour=8, minute=0, tzinfo=timezone.utc)
            search_end = datetime.combine(target_date, datetime.min.time()).replace(hour=18, minute=0, tzinfo=timezone.utc)

        slots = await client.find_free_slots(
            start=search_start.isoformat(),
            end=search_end.isoformat(),
            duration_minutes=duration,
        )

        if not slots:
            next_day_start = search_start + timedelta(days=1)
            next_day_end = search_end + timedelta(days=1)
            slots = await client.find_free_slots(
                start=next_day_start.isoformat(),
                end=next_day_end.isoformat(),
                duration_minutes=duration,
            )

        if slots:
            slot_start = slots[0]["start"]
            from dateutil.parser import isoparse
            start_dt = isoparse(slot_start)
            end_dt = start_dt + timedelta(minutes=duration)

            event = await client.create_event(
                subject=f"[TaskPilot] {instance.title}",
                start=start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                end=end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                body=instance.description or "",
                show_as="busy",
            )
            instance.calendar_event_id = event.get("id")
            logger.info(
                "Kalender-Blocker erstellt: '%s' (%d Min) fuer Task %s",
                instance.title, duration, instance.id,
            )
        else:
            logger.warning("Kein freier Slot fuer Kalender-Blocker: %s", instance.title)

    except Exception:
        logger.exception("Fehler beim Erstellen des Kalender-Blockers fuer Task %s", instance.id)
    finally:
        await client.close()


async def _check_and_spawn(db: AsyncSession) -> int:
    """Prüft alle Templates und erzeugt fällige Instanzen.
    Gibt die Anzahl neu erzeugter Instanzen zurück."""
    templates = await _get_templates(db)
    now = datetime.now(timezone.utc)
    spawned = 0

    for tmpl in templates:
        try:
            if not croniter.is_valid(tmpl.recurrence_rule):
                logger.warning("Ungültige Cron-Expression '%s' bei Task %s", tmpl.recurrence_rule, tmpl.id)
                continue

            if await _has_active_instance(db, tmpl.id):
                continue

            last_ts = await _latest_instance_time(db, tmpl.id)
            base_time = last_ts or tmpl.created_at
            cron = croniter(tmpl.recurrence_rule, base_time)
            next_run = cron.get_next(datetime)

            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)

            if next_run <= now:
                instance = await _copy_template(db, tmpl)
                spawned += 1
                logger.info(
                    "Recurring-Instanz '%s' (id=%s) aus Template %s erzeugt",
                    instance.title, instance.id, tmpl.id,
                )
        except Exception:
            logger.exception("Fehler bei Recurring-Check für Template %s", tmpl.id)

    return spawned


async def recurring_loop() -> None:
    """Endlosschleife, die periodisch recurring Tasks prüft."""
    logger.info("Recurring-Scheduler gestartet (Intervall: %ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            async with async_session() as db:
                count = await _check_and_spawn(db)
                await db.commit()
                if count:
                    logger.info("%d neue Recurring-Instanz(en) erzeugt", count)
        except Exception:
            logger.exception("Recurring-Scheduler: unerwarteter Fehler")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


_scheduler_task: asyncio.Task | None = None


async def start_recurring_scheduler() -> None:
    global _scheduler_task
    _scheduler_task = asyncio.create_task(recurring_loop())


async def stop_recurring_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
