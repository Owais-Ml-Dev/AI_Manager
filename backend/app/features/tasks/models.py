"""Database model for tasks. due_date/due_time apply to one-time tasks only."""
import enum
import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskCategory(str, enum.Enum):
    RECURRING = "recurring"
    ONE_TIME = "one_time"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Supabase Auth user id (auth.users.id). Cascade: deleting the Supabase
    # user deletes their tasks (and everything that cascades from tasks).
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    category: Mapped[TaskCategory] = mapped_column(
        Enum(TaskCategory, name="task_category", native_enum=True)
    )
    urgent: Mapped[bool] = mapped_column(Boolean)
    important: Mapped[bool] = mapped_column(Boolean)
    # One-time tasks only. Naive (no timezone yet, same deferral as elsewhere).
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    due_time: Mapped[time | None] = mapped_column(Time, default=None)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=True),
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
