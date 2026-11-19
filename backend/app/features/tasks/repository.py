"""Database queries for tasks. No business logic here — that's service.py's job."""
import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import text
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.tasks.models import Task, TaskCategory, TaskStatus


async def create(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    category: TaskCategory,
    description: str | None,
    urgent: bool,
    important: bool,
    due_date: date | None = None,
    due_time: time | None = None,
) -> Task:
    task = Task(
        user_id=user_id,
        title=title,
        category=category,
        description=description,
        urgent=urgent,
        important=important,
        due_date=due_date,
        due_time=due_time,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_all(db: AsyncSession, user_id: uuid.UUID) -> list[Task]:
    result = await db.execute(select(Task).where(Task.user_id == user_id).order_by(Task.id))
    return list(result.scalars().all())


async def get(db: AsyncSession, task_id: int) -> Task | None:
    return await db.get(Task, task_id)


async def update(db: AsyncSession, task: Task, fields: dict[str, Any]) -> Task:
    for key, value in fields.items():
        setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return task


async def delete(db: AsyncSession, task: Task) -> None:
    await db.execute(sql_delete(Task).where(Task.id == task.id))
    await db.commit()


async def mark_overdue(db: AsyncSession, default_timezone: str) -> None:
    """Flips PENDING one-time tasks past their deadline to OVERDUE, judged in
    EACH OWNER'S local time (user_settings.timezone, else default_timezone):
    a date-only task is overdue from local midnight after its due date
    (due_date + 24:00); with a due_time, once that local date+time passes.
    One statement for all users — Postgres converts now() into each owner's
    zone, so this stays a single query however many users there are."""
    await db.execute(
        text("""
            UPDATE tasks AS t
               SET status = 'OVERDUE', updated_at = now()
             WHERE t.category = 'ONE_TIME'
               AND t.status = 'PENDING'
               AND t.due_date IS NOT NULL
               AND (t.due_date + COALESCE(t.due_time, TIME '24:00'))
                   < (now() AT TIME ZONE COALESCE(
                        (SELECT us.timezone FROM user_settings us WHERE us.user_id = t.user_id),
                        :default_tz))
        """),
        {"default_tz": default_timezone},
    )
    await db.commit()
