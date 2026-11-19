"""Business logic for occurrences: one row per scheduled day of a recurring
task, completed/skipped independently per date.

Generation (insert-only, idempotent) happens when a schedule is saved and
once a day in the worker to extend the rolling horizon. Time-driven status
changes (missed, paused days skipped) are done by the worker
(app.features.maintenance) — listing occurrences only reads.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.features.occurrences import repository
from app.features.occurrences.models import Occurrence, OccurrenceStatus
from app.features.reminders import repository as reminders_repository
from app.features.reminders.service import ROLLING_HORIZON_DAYS, compute_eligible_dates, get_reminder_config
from app.features.tasks import repository as tasks_repository
from app.features.tasks.models import TaskCategory
from app.features.tasks.service import get_task


async def generate_occurrences(db: AsyncSession, task_id: int, today: date) -> None:
    """Creates any missing occurrence rows from the task's schedule up to the
    horizon (`today` = the owner's local date). Recurring tasks with a
    schedule only; a no-op otherwise. Does not commit."""
    task = await tasks_repository.get(db, task_id)
    if task is None or task.category != TaskCategory.RECURRING:
        return
    config = await reminders_repository.get_by_task_id(db, task_id)
    if config is None:
        return
    horizon = config.end_date if config.end_date else today + timedelta(days=ROLLING_HORIZON_DAYS)
    existing = await repository.get_existing_dates(db, task_id)
    new_dates = [d for d in compute_eligible_dates(config, horizon) if d not in existing]
    await repository.bulk_create(db, task_id, new_dates)


async def list_occurrences(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> list[Occurrence]:
    """Read-only."""
    task = await get_task(db, task_id, user_id)
    if task.category != TaskCategory.RECURRING:
        raise ValidationError("Occurrence tracking only applies to recurring tasks")
    await get_reminder_config(db, task_id, user_id)  # raises NotFoundError if no schedule set
    return await repository.list_by_task(db, task_id)


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
    updated = await repository.update_status(db, occurrence, status)
    await db.commit()
    return updated
