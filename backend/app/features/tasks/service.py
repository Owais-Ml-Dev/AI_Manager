"""Business logic for tasks."""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.features.history import service as history_service
from app.features.tasks import repository
from app.features.tasks.models import Task, TaskCategory

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
) -> Task:
    task = await repository.create(
        db, user_id, title, category, description, urgent, important, due_date, due_time
    )
    await history_service.record_created(db, task.id)
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

    return updated


async def delete_task(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> None:
    task = await get_task(db, task_id, user_id)
    await repository.delete(db, task)


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


async def sync_overdue(db: AsyncSession) -> None:
    """Flips PENDING one-time tasks past their due date/time to OVERDUE.

    Runs across all users (maintenance sweep, not a per-request user action).
    Deadline policy (consistent with occurrences' missed-detection): a task
    with only a due_date is overdue starting the day AFTER that date (the
    whole due date still counts as on-time). A task with a due_time is
    overdue once that exact date+time has passed.
    """
    now = datetime.now()
    await repository.mark_overdue(db, today=now.date(), now_time=now.time())
