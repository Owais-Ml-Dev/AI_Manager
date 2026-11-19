"""Time-driven state changes: things that become true just because time
passed (a deadline, a day ending). Run by the background worker every sweep
— never by GET requests, which only read.

Each change and its history event are ONE SQL statement (UPDATE ... RETURNING
feeding an INSERT), so they can't be separated, and two server processes
running this at once can't record the same event twice: the second UPDATE
finds the rows already changed and inserts nothing.

"Now" and "today" are each owner's LOCAL time (user_settings.timezone, else
settings.default_timezone), computed inside Postgres, so this stays a few
queries in total however many users there are.
"""
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# The owner's local "now" for task row `t` (timestamp without time zone).
_LOCAL_NOW = """(now() AT TIME ZONE COALESCE(
    (SELECT us.timezone FROM user_settings us WHERE us.user_id = t.user_id), :default_tz))"""


def _scope(task_id: int | None) -> tuple[str, dict]:
    params = {"default_tz": settings.default_timezone}
    if task_id is None:
        return "", params
    return " AND t.id = :task_id", {**params, "task_id": task_id}


async def mark_overdue(db: AsyncSession, task_id: int | None = None) -> int:
    """PENDING one-time tasks past their deadline -> OVERDUE, + a
    became_overdue history event. Date-only deadline: overdue from local
    midnight after the due date (due_date + 24:00); with a due_time, once
    that local date+time passes. Paused tasks are never touched."""
    scope, params = _scope(task_id)
    result = await db.execute(text(f"""
        WITH flipped AS (
            UPDATE tasks AS t
               SET status = 'OVERDUE', updated_at = now()
             WHERE t.category = 'ONE_TIME'
               AND t.status = 'PENDING'
               AND t.due_date IS NOT NULL
               AND (t.due_date + COALESCE(t.due_time, TIME '24:00')) < {_LOCAL_NOW}{scope}
         RETURNING t.id
        )
        INSERT INTO task_history_events (task_id, event_type, field_name, old_value, new_value, occurred_at)
        SELECT id, 'BECAME_OVERDUE', 'status', 'pending', 'overdue', now() FROM flipped
    """), params)
    return result.rowcount


async def skip_paused_days(db: AsyncSession, task_id: int | None = None) -> int:
    """Pending occurrences of a PAUSED recurring task whose local day has
    ended -> SKIPPED (a pause must not count as missed days). The task's
    paused/resumed events already record why, so no event per day."""
    scope, params = _scope(task_id)
    result = await db.execute(text(f"""
        UPDATE occurrences AS o
           SET status = 'SKIPPED'
          FROM tasks AS t
         WHERE o.task_id = t.id
           AND t.status = 'PAUSED'
           AND o.status = 'PENDING'
           AND o.occurrence_date < ({_LOCAL_NOW})::date{scope}
    """), params)
    return result.rowcount


async def mark_missed(db: AsyncSession, task_id: int | None = None) -> int:
    """Pending occurrences whose local day has ended -> MISSED, + an
    occurrence_missed history event (old_value = the occurrence date).
    Paused tasks are excluded (their days are skipped instead)."""
    scope, params = _scope(task_id)
    result = await db.execute(text(f"""
        WITH missed AS (
            UPDATE occurrences AS o
               SET status = 'MISSED'
              FROM tasks AS t
             WHERE o.task_id = t.id
               AND t.status <> 'PAUSED'
               AND o.status = 'PENDING'
               AND o.occurrence_date < ({_LOCAL_NOW})::date{scope}
         RETURNING o.task_id, o.occurrence_date
        )
        INSERT INTO task_history_events (task_id, event_type, field_name, old_value, new_value, occurred_at)
        SELECT task_id, 'OCCURRENCE_MISSED', 'occurrence_date', occurrence_date::text, 'missed', now()
          FROM missed
    """), params)
    return result.rowcount


async def apply_time_based_changes(db: AsyncSession, task_id: int | None = None) -> dict[str, int]:
    """All three, in the right order (paused days become skipped BEFORE the
    missed pass could claim them). Does not commit — callers own the
    transaction (the worker commits; write requests commit with their own
    changes)."""
    return {
        "overdue": await mark_overdue(db, task_id),
        "skipped": await skip_paused_days(db, task_id),
        "missed": await mark_missed(db, task_id),
    }


async def run_maintenance(db: AsyncSession) -> dict[str, int]:
    """Worker entry point: every user, every task; one commit."""
    counts = await apply_time_based_changes(db)
    await db.commit()
    return counts


async def extend_horizons(db: AsyncSession) -> None:
    """Once a day: keep the next ROLLING_HORIZON_DAYS of reminder deliveries
    and recurring occurrences generated, for every task with a schedule.
    Commits per task so one bad task can't hold back the rest."""
    from app.core.timezones import task_owner_zone, today_in
    from app.features.occurrences.service import generate_occurrences
    from app.features.reminders import repository as reminders_repository
    from app.features.reminders.service import generate_deliveries_for_task

    for task_id in await reminders_repository.list_task_ids_with_config(db):
        await generate_deliveries_for_task(db, task_id)
        today: date = today_in(await task_owner_zone(db, task_id))
        await generate_occurrences(db, task_id, today)
        await db.commit()
