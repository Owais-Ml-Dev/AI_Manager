"""Executes an already-validated, already-confirmed intent by calling the
same backend services every other endpoint uses — the assistant has no
special-cased write path. Called ONLY after explicit user confirmation
(except the two read-only intents, which never write anything)."""
import uuid
from datetime import date

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationError

from app.core.timezones import user_today
from app.features.assistant.schemas import PendingAction
from app.features.dashboard import service as dashboard_service
from app.features.occurrences import repository as occurrences_repository
from app.features.occurrences.models import OccurrenceStatus
from app.features.occurrences.service import update_occurrence
from app.features.tasks.models import TaskCategory, TaskStatus
from app.features.reminders import service as reminders_service
from app.features.reminders.models import DaySelectionType
from app.features.reminders.schemas import ReminderConfigWrite
from app.features.tasks.service import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    pause_task,
    resume_task,
    update_task,
)

_DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def describe_schedule(pending: PendingAction, today: date) -> str:
    """'every Mon, Wed and Fri at 07:00, starting today' — used in the
    confirmation question and the result message."""
    days = {
        "every_day": "every day", "weekdays": "on weekdays", "weekends": "on weekends",
        "custom_weekdays": "every " + _join([_DAY_NAMES[d] for d in pending.weekdays or []] or ["?"]),
        None: "every day",
    }[pending.day_selection]
    at = f" at {_join([t.strftime('%H:%M') for t in pending.times])}" if pending.times else " (no reminder time)"
    start = pending.start_date or today
    when = "starting today" if start == today else f"starting {start}"
    until = f" until {pending.end_date}" if pending.end_date else ""
    return f"{days}{at}, {when}{until}"


async def _apply_schedule(db: AsyncSession, user_id: uuid.UUID, task_id: int, pending: PendingAction,
                          start: date, end: date | None) -> None:
    """Sets the task's schedule and makes its reminder times exactly
    pending.times, in one transaction (reminders_service.replace_schedule),
    which also commits anything the caller staged before it (a new task)."""
    try:
        config = ReminderConfigWrite(
            start_date=start,
            end_date=end,
            day_selection_type=DaySelectionType(pending.day_selection or "every_day"),
            custom_weekdays=pending.weekdays or None if pending.day_selection == "custom_weekdays" else None,
        )
    except PydanticValidationError as exc:
        raise ValidationError(exc.errors()[0]["msg"].removeprefix("Value error, ")) from exc
    await reminders_service.replace_schedule(db, task_id, user_id, config, pending.times)


async def execute_create_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    today = await user_today(db, user_id)
    recurring = pending.category == "recurring"
    task = await create_task(
        db,
        user_id,
        title=pending.title,
        category=TaskCategory.RECURRING if recurring else TaskCategory.ONE_TIME,
        description=None,
        urgent=pending.urgent or False,
        important=pending.important or False,
        due_date=None if recurring else pending.due_date,
        due_time=None if recurring else pending.due_time,
        commit=False,
    )
    if not recurring and not pending.times:
        await db.commit()
        due = f", due {task.due_date}" + (f" at {task.due_time.strftime('%H:%M')}" if task.due_time else "") if task.due_date else ""
        return f'Created "{task.title}"{due}.'

    # Recurring (or one-time with reminder times): the task and its schedule
    # are ONE transaction — committed together by _apply_schedule. If any part
    # fails, nothing was committed and the caller rolls it all back.
    start = pending.start_date or today
    end = pending.end_date if recurring else (pending.due_date or start)
    await _apply_schedule(db, user_id, task.id, pending, start, end)
    kind = "recurring task" if recurring else "task"
    return f'Created {kind} "{task.title}": {describe_schedule(pending, today)}.'


async def execute_configure_reminder(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    today = await user_today(db, user_id)
    task = await get_task(db, pending.task_id, user_id)
    end = pending.end_date
    if task.category == TaskCategory.ONE_TIME and end is None:
        end = task.due_date  # the service still rejects a one-time schedule without an end
    await _apply_schedule(db, user_id, task.id, pending, pending.start_date or today, end)
    return f'Reminders for "{task.title}": {describe_schedule(pending.model_copy(update={"end_date": end}), today)}.'


async def execute_pause_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    task = await pause_task(db, pending.task_id, user_id)
    return f'Paused "{task.title}". Its reminders are off until you resume it.'


async def execute_resume_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    # Raises NewDueDateRequired if the due date passed while paused — the
    # conversation then asks for a new date (see service.handle_message).
    task = await resume_task(db, pending.task_id, user_id, pending.due_date, pending.due_time)
    due = f" New due date: {task.due_date}." if pending.due_date else ""
    return f'Resumed "{task.title}".{due}'


async def execute_update_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    fields = {}
    if pending.new_title:
        fields["title"] = pending.new_title
    if pending.urgent is not None:
        fields["urgent"] = pending.urgent
    if pending.important is not None:
        fields["important"] = pending.important
    task = await update_task(db, pending.task_id, user_id, fields)
    return f"Updated \"{task.title}\"."


async def execute_change_priority(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    return await execute_update_task(db, user_id, pending)


async def execute_delete_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    task = await get_task(db, pending.task_id, user_id)
    title = task.title
    await delete_task(db, pending.task_id, user_id)
    return f"Deleted \"{title}\"."


async def execute_complete_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    task = await get_task(db, pending.task_id, user_id)
    if task.category == TaskCategory.ONE_TIME:
        await update_task(db, pending.task_id, user_id, {"status": TaskStatus.COMPLETED})
        return f"Marked \"{task.title}\" as completed."

    # Recurring: completion is per-occurrence (today's), not the whole task.
    occurrence = await occurrences_repository.get_by_task_and_date(db, task.id, await user_today(db, user_id))
    if occurrence is None:
        return f"\"{task.title}\" has no scheduled occurrence for today."
    await update_occurrence(db, task.id, user_id, occurrence.id, OccurrenceStatus.COMPLETED)
    return f"Marked today's \"{task.title}\" as completed."


async def execute_retrieve_tasks(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    tasks = await list_tasks(db, user_id)
    pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]
    if not pending_tasks:
        return "You have no pending tasks."
    lines = [f"- {t.title}" for t in pending_tasks]
    return "Your pending tasks:\n" + "\n".join(lines)


async def execute_retrieve_stats(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    dashboard = await dashboard_service.get_dashboard(db, user_id)
    return (
        f"You have {dashboard.total_tasks} tasks total. "
        f"Overall completion: {dashboard.overall_completion_percentage}%. "
        f"Today: {dashboard.today_completed_occurrences} completed, "
        f"{dashboard.today_pending_occurrences} pending, "
        f"{dashboard.today_missed_occurrences} missed."
    )
