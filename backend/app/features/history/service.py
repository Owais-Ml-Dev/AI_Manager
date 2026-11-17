"""Recording helpers called by other features as a side effect of their own
writes (task create/update, schedule replace), plus the read path for a
task's history.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError
from app.features.history import repository
from app.features.history.models import HistoryEventType, TaskHistoryEvent


async def record_created(db: AsyncSession, task_id: int) -> None:
    await repository.create_event(db, task_id, HistoryEventType.CREATED)


async def record_field_update(
    db: AsyncSession, task_id: int, field_name: str, old_value, new_value
) -> None:
    await repository.create_event(
        db, task_id, HistoryEventType.FIELD_UPDATED, field_name, str(old_value), str(new_value)
    )


async def record_priority_change(
    db: AsyncSession, task_id: int, field_name: str, old_value, new_value
) -> None:
    await repository.create_event(
        db, task_id, HistoryEventType.PRIORITY_CHANGED, field_name, str(old_value), str(new_value)
    )


async def record_status_change(db: AsyncSession, task_id: int, old_status, new_status) -> None:
    from app.features.tasks.models import TaskStatus  # local import avoids a cross-feature cycle

    # Reopening is a status change too, but the spec calls it out as its own
    # recorded event: going from COMPLETED to anything else.
    event_type = (
        HistoryEventType.REOPENED
        if old_status == TaskStatus.COMPLETED and new_status != TaskStatus.COMPLETED
        else HistoryEventType.STATUS_CHANGED
    )
    await repository.create_event(
        db, task_id, event_type, "status", old_status.value, new_status.value
    )


async def record_schedule_change(
    db: AsyncSession, task_id: int, old_summary: str | None, new_summary: str
) -> None:
    await repository.create_event(
        db, task_id, HistoryEventType.SCHEDULE_CHANGED, "schedule", old_summary, new_summary
    )


async def get_history(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> list[TaskHistoryEvent]:
    from app.features.tasks.service import get_task  # local import avoids a cross-feature cycle

    await get_task(db, task_id, user_id)  # raises NotFoundError if not found/not owned
    return await repository.list_by_task(db, task_id)
