"""Queries for the monthly report — all scoped to a [start, end] date range
for a single user. Pure SQL/Python, no AI."""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.occurrences.models import Occurrence
from app.features.tasks.models import Task, TaskCategory


async def get_one_time_tasks_due_in_month(
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


async def get_occurrences_with_task_title(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[tuple[Occurrence, str]]:
    result = await db.execute(
        select(Occurrence, Task.title)
        .join(Task, Occurrence.task_id == Task.id)
        .where(
            Task.user_id == user_id,
            Task.category == TaskCategory.RECURRING,
            Occurrence.occurrence_date >= start,
            Occurrence.occurrence_date <= end,
        )
    )
    return list(result.all())


async def get_all_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[Task]:
    result = await db.execute(select(Task).where(Task.user_id == user_id))
    return list(result.scalars().all())
