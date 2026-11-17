"""Business logic for occurrences: computing eligible dates from a task's
reminder config (shared with one-time tasks — same date range + day
selection), generating occurrence rows on demand, sweeping missed
occurrences, and recording completion/skip independently per date.

No background worker generates these yet (deferred) — generation happens
whenever occurrences are listed for a task, which is why this is all
deterministic and idempotent. (Reminder *deliveries*, a separate concept, do
now have a real background worker — see app.features.reminders.worker.)
"""
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.features.occurrences import repository
from app.features.occurrences.models import Occurrence, OccurrenceStatus
from app.features.reminders import repository as reminders_repository
from app.features.reminders.service import ROLLING_HORIZON_DAYS, compute_eligible_dates, get_reminder_config
from app.features.tasks.models import TaskCategory
from app.features.tasks.service import get_task, list_tasks


async def sync_occurrences(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> list[Occurrence]:
    task = await get_task(db, task_id, user_id)
    if task.category != TaskCategory.RECURRING:
        raise ValidationError("Occurrence tracking only applies to recurring tasks")

    # raises NotFoundError if no reminder config set
    config = await get_reminder_config(db, task_id, user_id)

    today = date.today()
    horizon = config.end_date if config.end_date else today + timedelta(days=ROLLING_HORIZON_DAYS)

    eligible = compute_eligible_dates(config, horizon)
    existing = await repository.get_existing_dates(db, task_id)
    new_dates = [d for d in eligible if d not in existing]

    await repository.bulk_create(db, task_id, new_dates)
    await repository.mark_missed_before(db, task_id, today)

    return await repository.list_by_task(db, task_id)


async def sync_all_occurrences_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Syncs occurrences for every recurring task that has a reminder config set.

    Used by the dashboard (and anything else aggregating across all tasks) so
    counts reflect "today" even for tasks whose own /occurrences endpoint was
    never hit. Recurring tasks without a reminder config yet are skipped.
    """
    tasks = await list_tasks(db, user_id)
    for task in tasks:
        if task.category != TaskCategory.RECURRING:
            continue
        config = await reminders_repository.get_by_task_id(db, task.id)
        if config is None:
            continue
        await sync_occurrences(db, task.id, user_id)


async def update_occurrence(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, occurrence_id: int, status: OccurrenceStatus
) -> Occurrence:
    await get_task(db, task_id, user_id)  # ownership check — raises NotFoundError if not owned
    occurrence = await repository.get(db, occurrence_id)
    if occurrence is None or occurrence.task_id != task_id:
        raise NotFoundError(f"Occurrence {occurrence_id} not found for task {task_id}")
    if occurrence.status != OccurrenceStatus.PENDING:
        raise ValidationError(
            f"Occurrence {occurrence_id} is {occurrence.status.value}, not pending — cannot change it"
        )
    return await repository.update_status(db, occurrence, status)
