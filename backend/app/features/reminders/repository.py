"""Database queries for reminder configs, reminder times, and deliveries."""
import datetime as dt

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.reminders.models import DeliveryStatus, ReminderConfig, ReminderDelivery, ReminderTime
from app.features.reminders.schemas import ReminderConfigWrite


async def get_by_task_id(db: AsyncSession, task_id: int) -> ReminderConfig | None:
    result = await db.execute(select(ReminderConfig).where(ReminderConfig.task_id == task_id))
    return result.scalar_one_or_none()


async def upsert(db: AsyncSession, task_id: int, data: ReminderConfigWrite) -> ReminderConfig:
    existing = await get_by_task_id(db, task_id)
    if existing is not None:
        for key, value in data.model_dump().items():
            setattr(existing, key, value)
        config = existing
    else:
        config = ReminderConfig(task_id=task_id, **data.model_dump())
        db.add(config)

    await db.commit()
    await db.refresh(config)
    return config


async def list_times(db: AsyncSession, reminder_config_id: int) -> list[ReminderTime]:
    result = await db.execute(
        select(ReminderTime)
        .where(ReminderTime.reminder_config_id == reminder_config_id)
        .order_by(ReminderTime.time_of_day)
    )
    return list(result.scalars().all())


async def get_time(db: AsyncSession, time_id: int) -> ReminderTime | None:
    return await db.get(ReminderTime, time_id)


async def time_exists(
    db: AsyncSession, reminder_config_id: int, time_of_day: dt.time
) -> bool:
    result = await db.execute(
        select(ReminderTime.id).where(
            ReminderTime.reminder_config_id == reminder_config_id,
            ReminderTime.time_of_day == time_of_day,
        )
    )
    return result.scalar_one_or_none() is not None


async def create_time(
    db: AsyncSession, reminder_config_id: int, time_of_day: dt.time
) -> ReminderTime:
    reminder_time = ReminderTime(reminder_config_id=reminder_config_id, time_of_day=time_of_day)
    db.add(reminder_time)
    await db.commit()
    await db.refresh(reminder_time)
    return reminder_time


async def update_time(
    db: AsyncSession, reminder_time: ReminderTime, time_of_day: dt.time
) -> ReminderTime:
    reminder_time.time_of_day = time_of_day
    await db.commit()
    await db.refresh(reminder_time)
    return reminder_time


async def delete_time(db: AsyncSession, reminder_time: ReminderTime) -> None:
    await db.delete(reminder_time)
    await db.commit()


async def list_task_ids_with_config(db: AsyncSession) -> list[int]:
    """Every task (any user, any category) that has a reminder config — used
    by the background worker, which runs across all users, not one request's."""
    result = await db.execute(select(ReminderConfig.task_id))
    return list(result.scalars().all())


async def get_existing_delivery_slots(
    db: AsyncSession, task_id: int
) -> set[tuple[int, dt.datetime]]:
    result = await db.execute(
        select(ReminderDelivery.reminder_time_id, ReminderDelivery.scheduled_for).where(
            ReminderDelivery.task_id == task_id
        )
    )
    return set(result.all())


async def bulk_create_deliveries(
    db: AsyncSession, rows: list[tuple[int, int, dt.datetime]]
) -> None:
    """rows: list of (task_id, reminder_time_id, scheduled_for)."""
    if not rows:
        return
    db.add_all(
        ReminderDelivery(task_id=task_id, reminder_time_id=reminder_time_id, scheduled_for=scheduled_for)
        for task_id, reminder_time_id, scheduled_for in rows
    )
    await db.commit()


async def delete_future_scheduled_deliveries(db: AsyncSession, task_id: int, now: dt.datetime) -> None:
    """Drops not-yet-sent deliveries generated under a schedule that just
    changed; the worker regenerates them from the new schedule. Already
    sent/cancelled deliveries are history and are kept."""
    await db.execute(
        sql_delete(ReminderDelivery).where(
            ReminderDelivery.task_id == task_id,
            ReminderDelivery.status == DeliveryStatus.SCHEDULED,
            ReminderDelivery.scheduled_for > now,
        )
    )
    await db.commit()


async def list_due_scheduled(db: AsyncSession, now: dt.datetime) -> list[ReminderDelivery]:
    result = await db.execute(
        select(ReminderDelivery).where(
            ReminderDelivery.status == DeliveryStatus.SCHEDULED,
            ReminderDelivery.scheduled_for <= now,
        )
    )
    return list(result.scalars().all())


async def mark_delivery(
    db: AsyncSession, delivery: ReminderDelivery, status: DeliveryStatus, sent_at: dt.datetime | None
) -> None:
    delivery.status = status
    delivery.sent_at = sent_at
    await db.commit()


async def list_deliveries_by_task(db: AsyncSession, task_id: int) -> list[ReminderDelivery]:
    result = await db.execute(
        select(ReminderDelivery)
        .where(ReminderDelivery.task_id == task_id)
        .order_by(ReminderDelivery.scheduled_for)
    )
    return list(result.scalars().all())
