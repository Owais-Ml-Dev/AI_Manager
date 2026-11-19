"""User settings. Changing the time zone re-plans the user's upcoming
reminders, because "07:00" means a different instant in the new zone."""
import uuid

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationError
from app.core.config import settings
from app.core.timezones import now_utc
from app.features.profile.models import UserSettings
from app.features.profile.schemas import UserSettingsRead


async def get_settings(db: AsyncSession, user_id: uuid.UUID) -> UserSettingsRead:
    row = await db.get(UserSettings, user_id)
    if row is None:
        return UserSettingsRead(timezone=settings.default_timezone, is_default=True)
    return UserSettingsRead(timezone=row.timezone, is_default=False)


async def set_timezone(db: AsyncSession, user_id: uuid.UUID, tz_name: str) -> UserSettingsRead:
    # Python and Postgres each ship a zone database; both must know the name,
    # since overdue detection runs in SQL (AT TIME ZONE).
    known_to_db = (await db.execute(
        text("select 1 from pg_timezone_names where name = :tz"), {"tz": tz_name}
    )).scalar()
    if not known_to_db:
        raise ValidationError(f"Time zone {tz_name!r} is not supported")

    previous = (await get_settings(db, user_id)).timezone
    await db.execute(
        pg_insert(UserSettings)
        .values(user_id=user_id, timezone=tz_name)
        .on_conflict_do_update(
            index_elements=[UserSettings.user_id],
            set_={"timezone": tz_name, "updated_at": now_utc()},
        )
    )
    await db.commit()

    if tz_name != previous:
        await _replan_reminders(db, user_id)
    return UserSettingsRead(timezone=tz_name, is_default=False)


async def _replan_reminders(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Upcoming deliveries were computed in the old zone: drop the future
    scheduled ones and regenerate them in the new zone. Past/sent ones stay."""
    from app.features.reminders import repository as reminders_repository
    from app.features.reminders.service import generate_deliveries_for_task
    from app.features.tasks.models import Task

    task_ids = (await db.execute(select(Task.id).where(Task.user_id == user_id))).scalars().all()
    for task_id in task_ids:
        await reminders_repository.delete_future_scheduled_deliveries(db, task_id, now_utc())
        await generate_deliveries_for_task(db, task_id)
