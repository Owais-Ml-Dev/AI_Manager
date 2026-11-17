"""Business logic for reminder configs, reminder times, and the delivery
pipeline (generation + the sweep the background worker calls).

Shared by both one-time and recurring tasks: date range + day selection +
reminder times work identically for both. The only thing that differs is
completion behavior (handled by the tasks/occurrences features, not here).
"""
import datetime as dt
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.core.notifications import send_reminder_notification
from app.features.history import service as history_service
from app.features.reminders import repository
from app.features.reminders.models import (
    DaySelectionType,
    DeliveryStatus,
    ReminderConfig,
    ReminderDelivery,
    ReminderTime,
)
from app.features.reminders.schemas import ReminderConfigWrite
from app.features.tasks.models import TaskCategory
from app.features.tasks.service import get_task

# How far ahead to generate occurrences/reminder deliveries when a reminder
# config has no end_date (otherwise generation would be unbounded). Re-extends
# on every sync as "today" advances.
ROLLING_HORIZON_DAYS = 90


def compute_eligible_dates(config: ReminderConfig, cap_date: date) -> list[date]:
    lower = config.start_date
    upper = min(cap_date, config.end_date) if config.end_date else cap_date
    if upper < lower:
        return []

    if config.day_selection_type == DaySelectionType.EVERY_DAY:
        return [lower + timedelta(days=i) for i in range((upper - lower).days + 1)]

    if config.day_selection_type == DaySelectionType.WEEKDAYS:
        return [
            lower + timedelta(days=i)
            for i in range((upper - lower).days + 1)
            if (lower + timedelta(days=i)).isoweekday() <= 5
        ]

    if config.day_selection_type == DaySelectionType.WEEKENDS:
        return [
            lower + timedelta(days=i)
            for i in range((upper - lower).days + 1)
            if (lower + timedelta(days=i)).isoweekday() >= 6
        ]

    if config.day_selection_type == DaySelectionType.CUSTOM_WEEKDAYS:
        weekdays = set(config.custom_weekdays or [])
        return [
            lower + timedelta(days=i)
            for i in range((upper - lower).days + 1)
            if (lower + timedelta(days=i)).isoweekday() in weekdays
        ]

    if config.day_selection_type == DaySelectionType.CUSTOM_DATES:
        return sorted(d for d in (config.custom_dates or []) if lower <= d <= upper)

    return []  # pragma: no cover - all DaySelectionType members handled above


def _summarize(config: ReminderConfig) -> str:
    return (
        f"day_selection={config.day_selection_type.value} start={config.start_date} "
        f"end={config.end_date} custom_weekdays={config.custom_weekdays} "
        f"custom_dates={config.custom_dates}"
    )


async def set_reminder_config(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, data: ReminderConfigWrite
) -> ReminderConfig:
    task = await get_task(db, task_id, user_id)  # ownership check — raises NotFoundError if not owned
    if task.category == TaskCategory.ONE_TIME and data.end_date is None:
        raise ValidationError("end_date is required for one-time tasks")

    existing = await repository.get_by_task_id(db, task_id)
    old_summary = _summarize(existing) if existing else None

    config = await repository.upsert(db, task_id, data)

    if existing is not None:
        # The schedule changed: anything already generated for the future
        # under the old schedule is now wrong. Clear it so it regenerates
        # from the new one (occurrences on next sync, deliveries on next
        # worker sweep). Past/resolved records stay as history.
        from app.features.occurrences import repository as occurrences_repository

        await repository.delete_future_scheduled_deliveries(db, task_id, datetime.now())
        await occurrences_repository.delete_future_pending(db, task_id, date.today())

    await history_service.record_schedule_change(db, task_id, old_summary, _summarize(config))
    return config


async def get_reminder_config(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> ReminderConfig:
    await get_task(db, task_id, user_id)  # ownership check — raises NotFoundError if not owned
    config = await repository.get_by_task_id(db, task_id)
    if config is None:
        raise NotFoundError(f"No reminder config for task {task_id}")
    return config


async def list_reminder_times(
    db: AsyncSession, task_id: int, user_id: uuid.UUID
) -> list[ReminderTime]:
    config = await get_reminder_config(db, task_id, user_id)
    return await repository.list_times(db, config.id)


async def add_reminder_time(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, time_of_day: dt.time
) -> ReminderTime:
    config = await get_reminder_config(db, task_id, user_id)
    if await repository.time_exists(db, config.id, time_of_day):
        raise ValidationError(f"Reminder time {time_of_day} already exists for this task")
    return await repository.create_time(db, config.id, time_of_day)


async def _get_owned_reminder_time(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, time_id: int
) -> ReminderTime:
    config = await get_reminder_config(db, task_id, user_id)
    reminder_time = await repository.get_time(db, time_id)
    if reminder_time is None or reminder_time.reminder_config_id != config.id:
        raise NotFoundError(f"Reminder time {time_id} not found for task {task_id}")
    return reminder_time


async def update_reminder_time(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, time_id: int, time_of_day: dt.time
) -> ReminderTime:
    reminder_time = await _get_owned_reminder_time(db, task_id, user_id, time_id)
    if time_of_day != reminder_time.time_of_day and await repository.time_exists(
        db, reminder_time.reminder_config_id, time_of_day
    ):
        raise ValidationError(f"Reminder time {time_of_day} already exists for this task")
    return await repository.update_time(db, reminder_time, time_of_day)


async def delete_reminder_time(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, time_id: int
) -> None:
    reminder_time = await _get_owned_reminder_time(db, task_id, user_id, time_id)
    await repository.delete_time(db, reminder_time)


async def list_deliveries(
    db: AsyncSession, task_id: int, user_id: uuid.UUID
) -> list[ReminderDelivery]:
    await get_task(db, task_id, user_id)  # ownership check — raises NotFoundError if not owned
    return await repository.list_deliveries_by_task(db, task_id)


async def _generate_deliveries_for_task(db: AsyncSession, task_id: int, config: ReminderConfig) -> None:
    times = await repository.list_times(db, config.id)
    if not times:
        return

    today = date.today()
    horizon = config.end_date if config.end_date else today + timedelta(days=ROLLING_HORIZON_DAYS)
    eligible_dates = compute_eligible_dates(config, horizon)

    # Only slots still in the future: a slot whose time already passed when
    # it was generated (e.g. a start_date in the past) is not a reminder
    # anyone is waiting for — creating it would make the next sweep send a
    # burst of stale reminders. Generation runs every sweep, ahead of time,
    # so no legitimately upcoming slot is ever skipped by this.
    now = datetime.now()
    existing = await repository.get_existing_delivery_slots(db, task_id)
    new_rows = []
    for d in eligible_dates:
        for t in times:
            slot = datetime.combine(d, t.time_of_day)
            if slot > now and (t.id, slot) not in existing:
                new_rows.append((task_id, t.id, slot))
    await repository.bulk_create_deliveries(db, new_rows)


async def generate_all_deliveries(db: AsyncSession) -> None:
    """Generates any newly-eligible delivery rows for every task that has a
    reminder config, across all users. Called by the background worker."""
    for task_id in await repository.list_task_ids_with_config(db):
        config = await repository.get_by_task_id(db, task_id)
        if config is not None:
            await _generate_deliveries_for_task(db, task_id, config)


async def run_reminder_sweep(db: AsyncSession) -> int:
    """Processes every SCHEDULED delivery whose time has come: cancels it if
    the underlying task/occurrence is already completed/cancelled (spec:
    completed one-time tasks and completed/skipped occurrences must stop
    generating reminders), otherwise "sends" it via the notification stub.

    Returns the number of deliveries processed. Called by the background
    worker — runs across all users, not scoped to a request.
    """
    # Local imports avoid cross-feature import cycles at module load time.
    from app.features.occurrences import repository as occurrences_repository
    from app.features.occurrences.models import OccurrenceStatus
    from app.features.tasks import repository as tasks_repository
    from app.features.tasks.models import TaskStatus

    now = datetime.now()
    due = await repository.list_due_scheduled(db, now)

    for delivery in due:
        task = await tasks_repository.get(db, delivery.task_id)

        should_cancel = task is None or task.status == TaskStatus.CANCELLED
        if not should_cancel and task.category == TaskCategory.ONE_TIME:
            should_cancel = task.status == TaskStatus.COMPLETED
        elif not should_cancel and task.category == TaskCategory.RECURRING:
            occurrence = await occurrences_repository.get_by_task_and_date(
                db, task.id, delivery.scheduled_for.date()
            )
            should_cancel = occurrence is not None and occurrence.status in (
                OccurrenceStatus.COMPLETED,
                OccurrenceStatus.SKIPPED,
            )

        if should_cancel:
            await repository.mark_delivery(db, delivery, DeliveryStatus.CANCELLED, sent_at=None)
        else:
            send_reminder_notification(
                task.id, task.title if task else "(deleted task)", delivery.scheduled_for
            )
            await repository.mark_delivery(
                db, delivery, DeliveryStatus.SENT, sent_at=datetime.now(dt.timezone.utc)
            )

    return len(due)
