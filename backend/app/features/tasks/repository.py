"""Database queries for tasks. No business logic here — that's service.py's job."""
import uuid
from datetime import date, time
from typing import Any


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
    await db.flush()
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
    await db.flush()
    await db.refresh(task)
    return task


async def delete(db: AsyncSession, task: Task) -> None:
    await db.execute(sql_delete(Task).where(Task.id == task.id))
    await db.flush()
