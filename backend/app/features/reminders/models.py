"""Reminder date range + day-selection config, one per task (shared by both
one-time and recurring tasks), plus the specific clock times reminders should
fire at, plus the delivery log the background worker writes to.
"""
import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DaySelectionType(str, enum.Enum):
    EVERY_DAY = "every_day"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    CUSTOM_WEEKDAYS = "custom_weekdays"
    CUSTOM_DATES = "custom_dates"


class ReminderConfig(Base):
    __tablename__ = "reminder_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), unique=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    # Optional: no end_date means indefinite recurrence (recurring tasks only
    # — one-time tasks should always set an end_date per the spec).
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    day_selection_type: Mapped[DaySelectionType] = mapped_column(
        Enum(DaySelectionType, name="day_selection_type", native_enum=True)
    )
    # ISO weekday numbers, 1=Monday .. 7=Sunday. Only set when day_selection_type is CUSTOM_WEEKDAYS.
    custom_weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger), default=None)
    # Only set when day_selection_type is CUSTOM_DATES.
    custom_dates: Mapped[list[date] | None] = mapped_column(ARRAY(Date), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ReminderTime(Base):
    """A single clock time (naive, no timezone yet) a reminder config fires at."""

    __tablename__ = "reminder_times"
    __table_args__ = (UniqueConstraint("reminder_config_id", "time_of_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_config_id: Mapped[int] = mapped_column(
        ForeignKey("reminder_configs.id", ondelete="CASCADE")
    )
    time_of_day: Mapped[time] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DeliveryStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ReminderDelivery(Base):
    """One concrete (date, time) firing of a reminder_time, tracked through
    the background worker's sweep. Generated lazily (same rolling-horizon
    pattern as occurrences), same table serves both task categories.
    """

    __tablename__ = "reminder_deliveries"
    __table_args__ = (UniqueConstraint("reminder_time_id", "scheduled_for"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    reminder_time_id: Mapped[int] = mapped_column(
        ForeignKey("reminder_times.id", ondelete="CASCADE")
    )
    # Naive (no timezone yet, same deferral as elsewhere) — date+time combined.
    # Absolute instant (UTC). Computed from the reminder time-of-day in the
    # task owner's time zone (app.core.timezones.local_to_utc).
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", native_enum=True),
        default=DeliveryStatus.SCHEDULED,
        server_default=DeliveryStatus.SCHEDULED.name,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
