"""Executes an already-validated, already-confirmed intent by calling the
same backend services every other endpoint uses — the assistant has no
special-cased write path. Called ONLY after explicit user confirmation
(except the two read-only intents, which never write anything)."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import user_today
from app.features.assistant.schemas import PendingAction
from app.features.dashboard import service as dashboard_service
from app.features.occurrences import repository as occurrences_repository
from app.features.occurrences.models import OccurrenceStatus
from app.features.occurrences.service import update_occurrence
from app.features.tasks.models import TaskCategory, TaskStatus
from app.features.tasks.service import create_task, delete_task, get_task, list_tasks, update_task


async def execute_create_task(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> str:
    task = await create_task(
        db,
        user_id,
        title=pending.title,
        category=TaskCategory.ONE_TIME,
        description=None,
        urgent=pending.urgent or False,
        important=pending.important or False,
        due_date=pending.due_date,
    )
    return f"Created \"{task.title}\"" + (f", due {task.due_date}." if task.due_date else ".")


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
