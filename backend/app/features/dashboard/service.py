"""Business logic for the main dashboard and per-task analytics. Pure
arithmetic over counts already computed by the repository — no AI, per the
spec's requirement."""
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import user_today
from app.features.dashboard import repository
from app.features.dashboard.schemas import (
    CalendarActivity,
    CalendarDay,
    CalendarEntry,
    CalendarEntryType,
    CalendarRead,
    CalendarView,
    DashboardRead,
    MonthlyBreakdown,
    TaskAnalyticsRead,
)
from app.features.history import repository as history_repository
from app.features.occurrences import repository as occurrences_repository
from app.features.occurrences.models import OccurrenceStatus
from app.features.reminders import repository as reminders_repository
from app.features.tasks.models import TaskCategory, TaskStatus
from app.features.tasks.service import get_task


async def get_dashboard(db: AsyncSession, user_id: uuid.UUID) -> DashboardRead:
    counts = await repository.get_counts(db, user_id, today=await user_today(db, user_id))

    # Overall completion % = (completed one-time tasks + completed occurrences)
    # / (eligible one-time tasks + eligible occurrences). "Eligible" excludes
    # cancelled one-time tasks, future pending occurrences, and skipped
    # occurrences from the denominator — documented policy, not derived from
    # the spec's exact wording (it leaves this definition to the implementer).
    numerator = counts["completed_one_time_tasks"] + counts["completed_occurrences"]
    denominator = counts["eligible_one_time_tasks"] + counts["eligible_occurrences"]
    overall_completion_percentage = round(100 * numerator / denominator, 1) if denominator else 0.0

    return DashboardRead(
        total_tasks=counts["total_tasks"],
        active_recurring_tasks=counts["active_recurring_tasks"],
        pending_one_time_tasks=counts["pending_one_time_tasks"],
        completed_one_time_tasks=counts["completed_one_time_tasks"],
        overdue_one_time_tasks=counts["overdue_one_time_tasks"],
        today_scheduled_occurrences=counts["today_scheduled_occurrences"],
        today_completed_occurrences=counts["today_completed_occurrences"],
        today_pending_occurrences=counts["today_pending_occurrences"],
        today_missed_occurrences=counts["today_missed_occurrences"],
        overall_completion_percentage=overall_completion_percentage,
    )


async def get_task_analytics(db: AsyncSession, task_id: int, user_id: uuid.UUID) -> TaskAnalyticsRead:
    task = await get_task(db, task_id, user_id)

    base = TaskAnalyticsRead(
        task_id=task.id,
        title=task.title,
        description=task.description,
        category=task.category,
        status=task.status,
    )

    if task.category == TaskCategory.ONE_TIME:
        base.due_date = task.due_date
        base.due_time = task.due_time
        if task.status == TaskStatus.COMPLETED:
            base.completed_at = await history_repository.get_latest_completion_time(db, task.id)
        return base

    # Recurring task: pull the reminder config (if any) and its occurrences.
    config = await reminders_repository.get_by_task_id(db, task.id)
    if config is None:
        return base  # no reminder config set yet — just the basic fields

    base.start_date = config.start_date
    base.end_date = config.end_date
    base.day_selection_type = config.day_selection_type

    occurrences = await occurrences_repository.list_by_task(db, task.id)
    today = await user_today(db, user_id)

    base.total_scheduled_occurrences = len(occurrences)
    base.completed_occurrences = sum(1 for o in occurrences if o.status == OccurrenceStatus.COMPLETED)
    base.missed_occurrences = sum(1 for o in occurrences if o.status == OccurrenceStatus.MISSED)
    base.skipped_occurrences = sum(1 for o in occurrences if o.status == OccurrenceStatus.SKIPPED)
    base.pending_occurrences = sum(1 for o in occurrences if o.status == OccurrenceStatus.PENDING)

    # Same eligibility policy as the main dashboard: date has arrived, not skipped.
    eligible = [
        o for o in occurrences if o.occurrence_date <= today and o.status != OccurrenceStatus.SKIPPED
    ]
    base.completion_percentage = (
        round(100 * base.completed_occurrences / len(eligible), 1) if eligible else 0.0
    )

    base.calendar_history = [
        CalendarEntry(occurrence_date=o.occurrence_date, status=o.status) for o in occurrences
    ]

    months: dict[str, dict[str, int]] = defaultdict(
        lambda: {"scheduled": 0, "completed": 0, "missed": 0, "skipped": 0, "pending": 0}
    )
    for o in occurrences:
        key = o.occurrence_date.strftime("%Y-%m")
        months[key]["scheduled"] += 1
        months[key][o.status.value] += 1
    base.monthly_performance = [
        MonthlyBreakdown(month=month, **counts) for month, counts in sorted(months.items())
    ]

    return base


def _compute_range(view: CalendarView, anchor: date) -> tuple[date, date]:
    if view == CalendarView.DAILY:
        return anchor, anchor

    if view == CalendarView.WEEKLY:
        # Monday..Sunday week containing the anchor date.
        start = anchor - timedelta(days=anchor.isoweekday() - 1)
        return start, start + timedelta(days=6)

    # MONTHLY: the full calendar month containing the anchor date.
    start = anchor.replace(day=1)
    next_month = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, next_month - timedelta(days=1)


async def get_calendar(db: AsyncSession, user_id: uuid.UUID, view: CalendarView, anchor: date) -> CalendarRead:
    start, end = _compute_range(view, anchor)

    occurrence_rows = await repository.get_occurrences_in_range(db, user_id, start, end)
    one_time_tasks = await repository.get_one_time_due_in_range(db, user_id, start, end)

    by_date: dict[date, list[CalendarActivity]] = defaultdict(list)
    for occurrence, title, category in occurrence_rows:
        by_date[occurrence.occurrence_date].append(
            CalendarActivity(
                task_id=occurrence.task_id,
                title=title,
                category=category,
                entry_type=CalendarEntryType.OCCURRENCE,
                status=occurrence.status.value,
            )
        )
    for task in one_time_tasks:
        by_date[task.due_date].append(
            CalendarActivity(
                task_id=task.id,
                title=task.title,
                category=task.category,
                entry_type=CalendarEntryType.DUE_DATE,
                status=task.status.value,
            )
        )

    days = []
    current = start
    while current <= end:
        days.append(CalendarDay(date=current, activities=by_date.get(current, [])))
        current += timedelta(days=1)

    return CalendarRead(view=view, start_date=start, end_date=end, days=days)
