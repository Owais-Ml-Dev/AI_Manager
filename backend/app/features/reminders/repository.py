"""Database queries for reminder configs, reminder times, and deliveries."""
import datetime as dt

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


async def bulk_create_deliveries(
    db: AsyncSession, rows: list[tuple[int, int, dt.datetime]]
) -> None:
    """rows: list of (task_id, reminder_time_id, scheduled_for).

    Idempotent: slots that already exist are skipped by the database (unique
    on reminder_time_id + scheduled_for), so callers don't need to check
    first and concurrent generators can't collide.
    """
    if not rows:
        return
    created = dt.datetime.now(dt.timezone.utc)
    await db.execute(
        pg_insert(ReminderDelivery)
        .values(
            [
                {
                    "task_id": task_id,
                    "reminder_time_id": reminder_time_id,
                    "scheduled_for": scheduled_for,
                    "status": DeliveryStatus.SCHEDULED,
                    "created_at": created,
                }
                for task_id, reminder_time_id, scheduled_for in rows
            ]
        )
        .on_conflict_do_nothing(index_elements=["reminder_time_id", "scheduled_for"])
    )
    await db.commit()


async def delete_future_scheduled_for_time(
    db: AsyncSession, reminder_time_id: int, now: dt.datetime
) -> None:
    """Drops a reminder time's not-yet-sent deliveries after the time itself
    changed (they'd otherwise still fire at the old time)."""
    await db.execute(
        sql_delete(ReminderDelivery).where(
            ReminderDelivery.reminder_time_id == reminder_time_id,
            ReminderDelivery.status == DeliveryStatus.SCHEDULED,
            ReminderDelivery.scheduled_for > now,
        )
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


async def list_due_scheduled(
    db: AsyncSession, now: dt.datetime, limit: int
) -> list[ReminderDelivery]:
    """Oldest first, capped — after downtime a single sweep can't balloon."""
    result = await db.execute(
        select(ReminderDelivery)
        .where(
            ReminderDelivery.status == DeliveryStatus.SCHEDULED,
            ReminderDelivery.scheduled_for <= now,
        )
        .order_by(ReminderDelivery.scheduled_for)
        .limit(limit)
    )
    return list(result.scalars().all())


async def claim_delivery(
    db: AsyncSession, delivery_id: int, status: DeliveryStatus, sent_at: dt.datetime | None
) -> bool:
    """Atomically moves a delivery out of SCHEDULED. Returns False if another
    worker/process already claimed it — the caller must then not send it.
    This compare-and-set is what keeps multiple server processes from
    sending the same reminder twice."""
    result = await db.execute(
        sql_update(ReminderDelivery)
        .where(ReminderDelivery.id == delivery_id, ReminderDelivery.status == DeliveryStatus.SCHEDULED)
        .values(status=status, sent_at=sent_at)
    )
    await db.commit()
    return result.rowcount == 1


async def mark_delivery_failed(db: AsyncSession, delivery_id: int) -> None:
    await db.execute(
        sql_update(ReminderDelivery)
        .where(ReminderDelivery.id == delivery_id)
        .values(status=DeliveryStatus.FAILED, sent_at=None)
    )
    await db.commit()


async def list_deliveries_by_task(db: AsyncSession, task_id: int) -> list[ReminderDelivery]:
    result = await db.execute(
        select(ReminderDelivery)
        .where(ReminderDelivery.task_id == task_id)
        .order_by(ReminderDelivery.scheduled_for)
    )
    return list(result.scalars().all())
