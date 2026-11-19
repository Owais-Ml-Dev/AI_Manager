"""Aggregate queries across tasks + occurrences for the main dashboard.

Pure Python/SQL counts — no AI involved, per the spec's requirement that
Gemini must never calculate statistics.
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.occurrences.models import Occurrence, OccurrenceStatus
from app.features.tasks.models import Task, TaskCategory, TaskStatus


async def _count_tasks(db: AsyncSession, user_id: uuid.UUID, *filters) -> int:
    result = await db.execute(
        select(func.count()).select_from(Task).where(Task.user_id == user_id, *filters)
    )
    return result.scalar_one()


async def _count_occurrences(db: AsyncSession, user_id: uuid.UUID, *filters) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Occurrence)
        .join(Task, Occurrence.task_id == Task.id)
        .where(Task.user_id == user_id, *filters)
    )
    return result.scalar_one()


async def get_counts(db: AsyncSession, user_id: uuid.UUID, today: date) -> dict[str, int]:
    total_tasks = await _count_tasks(db, user_id)
    active_recurring_tasks = await _count_tasks(
        db, user_id, Task.category == TaskCategory.RECURRING, Task.status != TaskStatus.CANCELLED
    )
    pending_one_time_tasks = await _count_tasks(
        db, user_id, Task.category == TaskCategory.ONE_TIME, Task.status == TaskStatus.PENDING
    )
    completed_one_time_tasks = await _count_tasks(
        db, user_id, Task.category == TaskCategory.ONE_TIME, Task.status == TaskStatus.COMPLETED
    )
    overdue_one_time_tasks = await _count_tasks(
        db, user_id, Task.category == TaskCategory.ONE_TIME, Task.status == TaskStatus.OVERDUE
    )
    # "Eligible" one-time tasks exclude cancelled ones from the completion-rate denominator.
    eligible_one_time_tasks = await _count_tasks(
        db, user_id, Task.category == TaskCategory.ONE_TIME,
        Task.status.notin_([TaskStatus.CANCELLED, TaskStatus.PAUSED]),  # a pause doesn't hurt stats
    )

    today_scheduled_occurrences = await _count_occurrences(
        db, user_id, Occurrence.occurrence_date == today
    )
    today_completed_occurrences = await _count_occurrences(
        db, user_id, Occurrence.occurrence_date == today, Occurrence.status == OccurrenceStatus.COMPLETED
    )
    today_pending_occurrences = await _count_occurrences(
        db, user_id, Occurrence.occurrence_date == today, Occurrence.status == OccurrenceStatus.PENDING
    )
    today_missed_occurrences = await _count_occurrences(
        db, user_id, Occurrence.occurrence_date == today, Occurrence.status == OccurrenceStatus.MISSED
    )
    # "Eligible" occurrences are those whose date has arrived and that weren't
    # skipped — future pending occurrences never count in the denominator.
    eligible_occurrences = await _count_occurrences(
        db,
        user_id,
        Occurrence.occurrence_date <= today,
        Occurrence.status != OccurrenceStatus.SKIPPED,
    )
    completed_occurrences = await _count_occurrences(
        db, user_id, Occurrence.status == OccurrenceStatus.COMPLETED
    )

    return {
        "total_tasks": total_tasks,
        "active_recurring_tasks": active_recurring_tasks,
        "pending_one_time_tasks": pending_one_time_tasks,
        "completed_one_time_tasks": completed_one_time_tasks,
        "overdue_one_time_tasks": overdue_one_time_tasks,
        "eligible_one_time_tasks": eligible_one_time_tasks,
        "today_scheduled_occurrences": today_scheduled_occurrences,
        "today_completed_occurrences": today_completed_occurrences,
        "today_pending_occurrences": today_pending_occurrences,
        "today_missed_occurrences": today_missed_occurrences,
        "eligible_occurrences": eligible_occurrences,
        "completed_occurrences": completed_occurrences,
    }


async def get_occurrences_in_range(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[tuple[Occurrence, str, TaskCategory]]:
    """Occurrences (with their task's title/category) in [start, end]."""
    result = await db.execute(
        select(Occurrence, Task.title, Task.category)
        .join(Task, Occurrence.task_id == Task.id)
        .where(
            Task.user_id == user_id,
            Occurrence.occurrence_date >= start,
            Occurrence.occurrence_date <= end,
        )
    )
    return list(result.all())


async def get_one_time_due_in_range(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[Task]:
    result = await db.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.category == TaskCategory.ONE_TIME,
            Task.due_date >= start,
            Task.due_date <= end,
        )
    )
    return list(result.scalars().all())
