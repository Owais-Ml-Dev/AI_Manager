"""Database queries for occurrences."""
from datetime import date, datetime, timezone

from sqlalchemy import select, update
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
    if not dates:
        return
    db.add_all(Occurrence(task_id=task_id, occurrence_date=d) for d in dates)
    await db.commit()


async def mark_missed_before(db: AsyncSession, task_id: int, today: date) -> None:
    await db.execute(
        update(Occurrence)
        .where(
            Occurrence.task_id == task_id,
            Occurrence.status == OccurrenceStatus.PENDING,
            Occurrence.occurrence_date < today,
        )
        .values(status=OccurrenceStatus.MISSED)
    )
    await db.commit()


async def update_status(
    db: AsyncSession, occurrence: Occurrence, status: OccurrenceStatus
) -> Occurrence:
    occurrence.status = status
    occurrence.completed_at = datetime.now(timezone.utc) if status == OccurrenceStatus.COMPLETED else None
    await db.commit()
    await db.refresh(occurrence)
    return occurrence
