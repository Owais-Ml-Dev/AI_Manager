"""Read-only dashboard + per-task analytics + calendar responses. Nothing
here is persisted — computed fresh from tasks/occurrences/history on every
request."""
import enum
from datetime import date, datetime, time

from pydantic import BaseModel

from app.features.occurrences.models import OccurrenceStatus
from app.features.reminders.models import DaySelectionType
from app.features.tasks.models import TaskCategory, TaskStatus


class DashboardRead(BaseModel):
    total_tasks: int
    active_recurring_tasks: int
    pending_one_time_tasks: int
    completed_one_time_tasks: int
    overdue_one_time_tasks: int
    today_scheduled_occurrences: int
    today_completed_occurrences: int
    today_pending_occurrences: int
    today_missed_occurrences: int
    overall_completion_percentage: float


class CalendarEntry(BaseModel):
    occurrence_date: date
    status: OccurrenceStatus


class MonthlyBreakdown(BaseModel):
    month: str  # "YYYY-MM"
    scheduled: int
    completed: int
    missed: int
    skipped: int
    pending: int


class TaskAnalyticsRead(BaseModel):
    task_id: int
    title: str
    description: str | None
    category: TaskCategory
    status: TaskStatus

    # One-time tasks only (None for recurring).
    due_date: date | None = None
    due_time: time | None = None
    completed_at: datetime | None = None

    # Recurring tasks only (None for one-time, and None until a reminder
    # config/occurrences exist).
    start_date: date | None = None
    end_date: date | None = None
    day_selection_type: DaySelectionType | None = None
    total_scheduled_occurrences: int | None = None
    completed_occurrences: int | None = None
    missed_occurrences: int | None = None
    skipped_occurrences: int | None = None
    pending_occurrences: int | None = None
    completion_percentage: float | None = None
    calendar_history: list[CalendarEntry] | None = None
    monthly_performance: list[MonthlyBreakdown] | None = None


class CalendarView(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class CalendarEntryType(str, enum.Enum):
    OCCURRENCE = "occurrence"  # a recurring task's scheduled occurrence
    DUE_DATE = "due_date"  # a one-time task's due date


class CalendarActivity(BaseModel):
    task_id: int
    title: str
    category: TaskCategory
    entry_type: CalendarEntryType
    status: str  # OccurrenceStatus or TaskStatus value, depending on entry_type


class CalendarDay(BaseModel):
    date: date
    activities: list[CalendarActivity]


class CalendarRead(BaseModel):
    view: CalendarView
    start_date: date
    end_date: date
    days: list[CalendarDay]
