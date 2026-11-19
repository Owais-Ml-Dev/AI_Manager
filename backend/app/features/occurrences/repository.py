"""Database queries for occurrences."""
from datetime import date, datetime, timezone

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.occurrences.models import Occurrence, OccurrenceStatus


async def list_by_task(db: AsyncSession, task_id: int) -> list[Occurrence]:
    result = await db.execute(
        select(Occurrence).where(Occurrence.task_id == task_id).order_by(Occurrence.occurrence_date)
    )
    return list(result.scalars().all())


async def get_existing_dates(db: AsyncSession, task_id: int) -> set[date]:
    result = await db.execute(
        select(Occurrence.occurrence_date).where(Occurrence.task_id == task_id)
    )
    return set(result.scalars().all())


async def get(db: AsyncSession, occurrence_id: int) -> Occurrence | None:
    return await db.get(Occurrence, occurrence_id)


async def get_by_task_and_date(db: AsyncSession, task_id: int, occurrence_date: date) -> Occurrence | None:
    result = await db.execute(
        select(Occurrence).where(
            Occurrence.task_id == task_id, Occurrence.occurrence_date == occurrence_date
        )
    )
    return result.scalar_one_or_none()


async def bulk_create(db: AsyncSession, task_id: int, dates: list[date]) -> None:
    """Idempotent: two concurrent syncs of the same task (e.g. dashboard +
    occurrences endpoint) can both decide a date is missing — ON CONFLICT DO
    NOTHING lets the second insert become a no-op instead of a 500."""
    if not dates:
        return
    now = datetime.now(timezone.utc)
    await db.execute(
        pg_insert(Occurrence)
        .values(
            [
                {"task_id": task_id, "occurrence_date": d, "created_at": now, "updated_at": now}
                for d in dates
            ]
        )
        .on_conflict_do_nothing(index_elements=["task_id", "occurrence_date"])
    )
    await db.flush()


async def delete_future_pending(db: AsyncSession, task_id: int, today: date) -> None:
    """Drops pending occurrences from today on, generated under a schedule
    that just changed; the next sync regenerates them from the new schedule.
    Completed/missed/skipped occurrences are history and are kept (spec:
    schedule edits must not overwrite past records)."""
    await db.execute(
        sql_delete(Occurrence).where(
            Occurrence.task_id == task_id,
            Occurrence.status == OccurrenceStatus.PENDING,
            Occurrence.occurrence_date >= today,
        )
    )
    await db.flush()


async def update_status(
    db: AsyncSession, occurrence: Occurrence, status: OccurrenceStatus
) -> Occurrence:
    occurrence.status = status
    occurrence.completed_at = datetime.now(timezone.utc) if status == OccurrenceStatus.COMPLETED else None
    await db.flush()
    await db.refresh(occurrence)
    return occurrence
