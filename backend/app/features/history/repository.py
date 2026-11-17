"""Database queries for task history events."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.history.models import HistoryEventType, TaskHistoryEvent


async def create_event(
    db: AsyncSession,
    task_id: int,
    event_type: HistoryEventType,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> TaskHistoryEvent:
    event = TaskHistoryEvent(
        task_id=task_id,
        event_type=event_type,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_by_task(db: AsyncSession, task_id: int) -> list[TaskHistoryEvent]:
    result = await db.execute(
        select(TaskHistoryEvent)
        .where(TaskHistoryEvent.task_id == task_id)
        .order_by(TaskHistoryEvent.occurred_at)
    )
    return list(result.scalars().all())


async def get_latest_completion_time(db: AsyncSession, task_id: int) -> datetime | None:
    result = await db.execute(
        select(TaskHistoryEvent.occurred_at)
        .where(
            TaskHistoryEvent.task_id == task_id,
            TaskHistoryEvent.field_name == "status",
            TaskHistoryEvent.new_value == "completed",
        )
        .order_by(TaskHistoryEvent.occurred_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
