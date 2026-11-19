"""Per-user time zones: the single place that answers "what time / what day
is it for this user?" and turns a user's local date + time into an absolute
instant.

Storage rule: absolute moments (reminder deliveries, history, created_at) are
stored as UTC timestamps. Calendar concepts (due dates, occurrence dates,
reminder times-of-day, "today") are LOCAL to the user and are interpreted in
the user's zone (user_settings.timezone, default settings.default_timezone).

Daylight saving: a local time that doesn't exist (clocks jump forward, e.g.
02:30 in New York on the March change) resolves to the moment after the jump
(03:30); a local time that happens twice (clocks fall back) resolves to the
first one. That is Python's fold=0 behaviour, relied on deliberately here.
"""
import uuid
from datetime import date, datetime, time, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


@lru_cache(maxsize=512)
def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def is_valid_zone(name: str) -> bool:
    # Only real IANA region names; "UTC" is accepted, abbreviations like
    # "IST"/"EST" are not (ambiguous) — zoneinfo rejects most of those.
    if not name or name != name.strip() or "/" not in name and name != "UTC":
        return False
    try:
        zone(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def default_zone() -> ZoneInfo:
    return zone(settings.default_timezone)


async def user_zone(db: AsyncSession, user_id: uuid.UUID) -> ZoneInfo:
    name = (await db.execute(
        text("select timezone from user_settings where user_id = :uid"), {"uid": user_id}
    )).scalar()
    return zone(name) if name else default_zone()


async def task_owner_zone(db: AsyncSession, task_id: int) -> ZoneInfo:
    name = (await db.execute(
        text("select us.timezone from tasks t left join user_settings us on us.user_id = t.user_id "
             "where t.id = :tid"), {"tid": task_id}
    )).scalar()
    return zone(name) if name else default_zone()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_in(tz: ZoneInfo, now: datetime | None = None) -> date:
    """The calendar date it currently is in `tz`."""
    return (now or now_utc()).astimezone(tz).date()


async def user_today(db: AsyncSession, user_id: uuid.UUID) -> date:
    return today_in(await user_zone(db, user_id))


def local_to_utc(day: date, at: time, tz: ZoneInfo) -> datetime:
    """The absolute (UTC) instant of local `day` `at` in `tz` (see the
    daylight-saving note in the module docstring)."""
    return datetime.combine(day, at.replace(tzinfo=None), tzinfo=tz).astimezone(timezone.utc)
