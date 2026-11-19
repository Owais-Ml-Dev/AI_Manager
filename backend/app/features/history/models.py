"""An append-only event log per task. Never updated or deleted once written —
that's what makes it a history. Occurrence-level history for recurring tasks
already lives in the occurrences table itself; this covers the task-level
events the spec calls out: creation, field updates, priority changes, status
changes (including reopening), and recurring-schedule changes.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HistoryEventType(str, enum.Enum):
    CREATED = "created"
    FIELD_UPDATED = "field_updated"
    PRIORITY_CHANGED = "priority_changed"
    STATUS_CHANGED = "status_changed"
    REOPENED = "reopened"
    SCHEDULE_CHANGED = "schedule_changed"
    # Recorded automatically by the background worker:
    BECAME_OVERDUE = "became_overdue"
    OCCURRENCE_MISSED = "occurrence_missed"  # old_value = the occurrence date
    # Recorded by pause/resume:
    PAUSED = "paused"
    RESUMED = "resumed"


class TaskHistoryEvent(Base):
    __tablename__ = "task_history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    event_type: Mapped[HistoryEventType] = mapped_column(
        Enum(HistoryEventType, name="history_event_type", native_enum=True)
    )
    field_name: Mapped[str | None] = mapped_column(String(100), default=None)
    old_value: Mapped[str | None] = mapped_column(String(500), default=None)
    new_value: Mapped[str | None] = mapped_column(String(500), default=None)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
