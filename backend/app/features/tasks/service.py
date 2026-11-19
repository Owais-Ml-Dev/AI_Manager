"""Business logic for tasks.

Every public write commits ONCE at the end, so the task change, its history
events and any reminder changes are saved together or not at all.
"""
import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.core.timezones import now_utc, user_zone
from app.features.history import service as history_service
from app.features.tasks import repository
from app.features.tasks.models import Task, TaskCategory, TaskStatus


class NewDueDateRequired(ValidationError):
    """Resuming a one-time task whose due date passed while it was paused:
    the user must choose a new due date (the app shows a date picker)."""

# Fields whose changes get logged as PRIORITY_CHANGED instead of plain FIELD_UPDATED.
PRIORITY_FIELDS = {"urgent", "important"}
# Fields worth recording on update; "status" is handled separately (reopening detection).
TRACKED_FIELDS = {"title", "description", "due_date", "due_time", "urgent", "important"}


async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    category: TaskCategory,
    description: str | None,
    urgent: bool,
    important: bool,
    due_date: date | None = None,
    due_time=None,
    commit: bool = True,
) -> Task:
    """commit=False lets a caller save more in the same transaction (the
    assistant creates a recurring task and its schedule as one unit)."""
    task = await repository.create(
        db, user_id, title, category, description, urgent, important, due_date, due_time
    )
    await history_service.record_created(db, task.id)
    if commit:
        await db.commit()
    return task


async def list_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[Task]:
    return await repository.list_all(db, user_id)


async def get_task(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> Task:
    """Raises NotFoundError both when the task doesn't exist AND when it
    exists but belongs to someone else — never reveals which, to avoid
    leaking the existence of other users' tasks."""
    task = await repository.get(db, task_id)
    if task is None or task.user_id != user_id:
        raise NotFoundError(f"Task {task_id} not found")
    return task


async def update_task(
    db: AsyncSession, task_id: int, user_id: uuid.UUID, fields: dict[str, Any]
) -> Task:
    task = await get_task(db, task_id, user_id)

    touches_due = "due_date" in fields or "due_time" in fields
    if touches_due:
        if task.category != TaskCategory.ONE_TIME:
            raise ValidationError("due_date/due_time only apply to one-time tasks")
        resulting_due_date = fields.get("due_date", task.due_date)
        resulting_due_time = fields.get("due_time", task.due_time)
        if resulting_due_time is not None and resulting_due_date is None:
            raise ValidationError("due_time requires due_date to be set")

    if "status" in fields and fields["status"] != task.status:
        # Pausing/resuming has its own rules (reminders, skipped days, a new
        # due date) — only the dedicated endpoints do it. A paused task may
        # still be completed or cancelled directly.
        if fields["status"] == TaskStatus.PAUSED or (
            task.status == TaskStatus.PAUSED
            and fields["status"] not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ):
            raise ValidationError("Use POST /tasks/{id}/pause and /tasks/{id}/resume to pause or resume a task")

    # Snapshot old values before repository.update() mutates the same object in place.
    old_status = task.status
    old_values = {field: getattr(task, field) for field in fields if field in TRACKED_FIELDS}

    updated = await repository.update(db, task, fields)

    if "status" in fields and fields["status"] != old_status:
        await history_service.record_status_change(db, task_id, old_status, fields["status"])

    for field, old_value in old_values.items():
        new_value = fields[field]
        if new_value == old_value:
            continue
        if field in PRIORITY_FIELDS:
            await history_service.record_priority_change(db, task_id, field, old_value, new_value)
        else:
            await history_service.record_field_update(db, task_id, field, old_value, new_value)

    await db.commit()
    return updated


async def delete_task(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> None:
    task = await get_task(db, task_id, user_id)
    await repository.delete(db, task)
    await db.commit()


def _quadrant_key(task: Task) -> str:
    """Eisenhower Matrix quadrant, derived from urgent/important — never stored."""
    if task.urgent and task.important:
        return "do_first"
    if task.important:
        return "schedule"
    if task.urgent:
        return "delegate"
    return "eliminate"


async def get_matrix(
    db: AsyncSession, user_id: uuid.UUID, category: TaskCategory | None = None
) -> dict[str, list[Task]]:
    tasks = await list_tasks(db, user_id)
    if category is not None:
        tasks = [t for t in tasks if t.category == category]

    groups: dict[str, list[Task]] = {"do_first": [], "schedule": [], "delegate": [], "eliminate": []}
    for task in tasks:
        groups[_quadrant_key(task)].append(task)
    return groups


def _deadline_passed(due_date: date, due_time: time | None, local_now: datetime) -> bool:
    """Same rule as overdue detection: date-only is due through the whole
    local day; with a time, until that local date+time."""
    if due_time is None:
        return local_now.date() > due_date
    return local_now.replace(tzinfo=None) > datetime.combine(due_date, due_time)


async def pause_task(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> Task:
    """While paused: no reminders, never overdue, recurring days are skipped
    (not missed). Allowed from pending or overdue."""
    from app.features.reminders import repository as reminders_repository

    task = await get_task(db, task_id, user_id)
    if task.status not in (TaskStatus.PENDING, TaskStatus.OVERDUE):
        raise ValidationError(f"Only pending or overdue tasks can be paused (this one is {task.status.value})")
    old_status = task.status
    updated = await repository.update(db, task, {"status": TaskStatus.PAUSED})
    await history_service.record_paused(db, task_id, old_status)
    await reminders_repository.delete_future_scheduled_deliveries(db, task_id, now_utc())
    await db.commit()
    return updated


async def resume_task(
    db: AsyncSession,
    task_id: int,
    user_id: uuid.UUID,
    due_date: date | None = None,
    due_time: time | None = None,
) -> Task:
    """Back to pending. A one-time task whose deadline passed during the
    pause needs a NEW future due date (NewDueDateRequired otherwise) — it is
    never silently turned overdue. Recurring: days missed while paused are
    recorded as skipped, and upcoming reminders are planned again."""
    from app.features.maintenance.service import skip_paused_days
    from app.features.reminders.service import generate_deliveries_for_task

    task = await get_task(db, task_id, user_id)
    if task.status != TaskStatus.PAUSED:
        raise ValidationError(f"Only paused tasks can be resumed (this one is {task.status.value})")

    fields: dict[str, Any] = {}
    if task.category == TaskCategory.RECURRING:
        if due_date is not None or due_time is not None:
            raise ValidationError("due_date/due_time only apply to one-time tasks")
        await skip_paused_days(db, task_id)  # while still paused: those days are skipped, not missed
    else:
        if due_time is not None and due_date is None:
            raise ValidationError("due_time requires due_date")
        local_now = now_utc().astimezone(await user_zone(db, user_id))
        if due_date is not None:
            if _deadline_passed(due_date, due_time, local_now):
                raise ValidationError("The new due date/time is already in the past")
            fields = {"due_date": due_date, "due_time": due_time}
        elif task.due_date is not None and _deadline_passed(task.due_date, task.due_time, local_now):
            raise NewDueDateRequired(
                f"The due date ({task.due_date}) passed while the task was paused — choose a new due_date to resume"
            )

    old_values = {f: getattr(task, f) for f in fields}
    updated = await repository.update(db, task, {**fields, "status": TaskStatus.PENDING})
    for field, old_value in old_values.items():
        if fields[field] != old_value:
            await history_service.record_field_update(db, task_id, field, old_value, fields[field])
    await history_service.record_resumed(db, task_id)
    await generate_deliveries_for_task(db, task_id)
    await db.commit()
    return updated
