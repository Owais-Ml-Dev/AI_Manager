"""Business logic for the monthly report. Pure Python/arithmetic over data
already in the database — no AI, per the spec's requirement."""
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.occurrences.models import OccurrenceStatus
from app.features.reports import repository
from app.features.reports.schemas import (
    DailyTrendPoint,
    EisenhowerMonthlyAnalysis,
    IndividualTaskMonthlyPerformance,
    MonthlyReportRead,
    OneTimeMonthlyPerformance,
    OverallProductivity,
    QuadrantSummary,
    RecurringMonthlyPerformance,
    WeeklyTrendPoint,
)
from app.features.tasks.models import TaskStatus


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _quadrant_key(task) -> str:
    if task.urgent and task.important:
        return "do_first"
    if task.important:
        return "schedule"
    if task.urgent:
        return "delegate"
    return "eliminate"


async def get_monthly_report(
    db: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> MonthlyReportRead:
    start, end = _month_range(year, month)
    today = date.today()

    # --- A. One-time task performance ---
    one_time_tasks = await repository.get_one_time_tasks_due_in_month(db, user_id, start, end)
    ot_completed = sum(1 for t in one_time_tasks if t.status == TaskStatus.COMPLETED)
    ot_overdue = sum(1 for t in one_time_tasks if t.status == TaskStatus.OVERDUE)
    ot_remaining = sum(1 for t in one_time_tasks if t.status == TaskStatus.PENDING)
    ot_eligible = ot_completed + ot_overdue + ot_remaining  # cancelled excluded
    one_time_performance = OneTimeMonthlyPerformance(
        completed=ot_completed,
        overdue=ot_overdue,
        remaining=ot_remaining,
        completion_percentage=round(100 * ot_completed / ot_eligible, 1) if ot_eligible else 0.0,
    )

    # --- B & C. Recurring task performance (overall + per task) ---
    occ_rows = await repository.get_occurrences_with_task_title(db, user_id, start, end)
    per_task: dict[int, dict] = defaultdict(
        lambda: {
            "title": "",
            "scheduled": 0,
            "completed": 0,
            "missed": 0,
            "skipped": 0,
            "pending": 0,
            "eligible": 0,
        }
    )
    scheduled = completed = missed = skipped = 0
    eligible_total = completed_total_for_rate = 0
    daily_completed: dict[date, int] = defaultdict(int)

    for occurrence, title in occ_rows:
        scheduled += 1
        status = occurrence.status
        per_task[occurrence.task_id]["title"] = title
        per_task[occurrence.task_id]["scheduled"] += 1
        per_task[occurrence.task_id][status.value] += 1

        if status == OccurrenceStatus.COMPLETED:
            completed += 1
            daily_completed[occurrence.occurrence_date] += 1
        elif status == OccurrenceStatus.MISSED:
            missed += 1
        elif status == OccurrenceStatus.SKIPPED:
            skipped += 1

        if status != OccurrenceStatus.SKIPPED and occurrence.occurrence_date <= today:
            eligible_total += 1
            per_task[occurrence.task_id]["eligible"] += 1
            if status == OccurrenceStatus.COMPLETED:
                completed_total_for_rate += 1

    recurring_performance = RecurringMonthlyPerformance(
        scheduled_occurrences=scheduled,
        completed_occurrences=completed,
        missed_occurrences=missed,
        skipped_occurrences=skipped,
        completion_rate=round(100 * completed_total_for_rate / eligible_total, 1) if eligible_total else 0.0,
    )

    individual_task_performance = []
    consistency_percentages = []
    for task_id, counts in per_task.items():
        # Same eligibility policy as the overall recurring rate: excludes
        # skipped occurrences and any occurrence whose date hasn't arrived yet.
        task_eligible = counts["eligible"]
        task_completed = counts["completed"]
        pct = round(100 * task_completed / task_eligible, 1) if task_eligible else 0.0
        individual_task_performance.append(
            IndividualTaskMonthlyPerformance(
                task_id=task_id,
                title=counts["title"],
                scheduled=counts["scheduled"],
                completed=counts["completed"],
                missed=counts["missed"],
                skipped=counts["skipped"],
                completion_percentage=pct,
            )
        )
        consistency_percentages.append(pct)
    individual_task_performance.sort(key=lambda t: t.title)

    # --- D. Eisenhower Matrix analysis (live snapshot, not month-filtered) ---
    all_tasks = await repository.get_all_tasks(db, user_id)
    quadrants = {
        "do_first": {"total": 0, "completed": 0, "pending": 0},
        "schedule": {"total": 0, "completed": 0, "pending": 0},
        "delegate": {"total": 0, "completed": 0, "pending": 0},
        "eliminate": {"total": 0, "completed": 0, "pending": 0},
    }
    for task in all_tasks:
        q = quadrants[_quadrant_key(task)]
        q["total"] += 1
        if task.status == TaskStatus.COMPLETED:
            q["completed"] += 1
        elif task.status == TaskStatus.PENDING:
            q["pending"] += 1
    eisenhower_analysis = EisenhowerMonthlyAnalysis(
        do_first=QuadrantSummary(**quadrants["do_first"]),
        schedule=QuadrantSummary(**quadrants["schedule"]),
        delegate=QuadrantSummary(**quadrants["delegate"]),
        eliminate=QuadrantSummary(**quadrants["eliminate"]),
    )

    # --- E. Overall productivity ---
    for task in one_time_tasks:
        if task.status == TaskStatus.COMPLETED:
            daily_completed[task.due_date] += 1

    daily_trends = [
        DailyTrendPoint(date=d, completed_count=c) for d, c in sorted(daily_completed.items())
    ]

    weekly_totals: dict[date, int] = defaultdict(int)
    for d, c in daily_completed.items():
        week_start = d - timedelta(days=d.isoweekday() - 1)
        weekly_totals[week_start] += c
    weekly_trends = [
        WeeklyTrendPoint(week_start=ws, week_end=ws + timedelta(days=6), completed_count=c)
        for ws, c in sorted(weekly_totals.items())
    ]

    overall_numerator = ot_completed + completed_total_for_rate
    overall_denominator = ot_eligible + eligible_total
    monthly_completion_percentage = (
        round(100 * overall_numerator / overall_denominator, 1) if overall_denominator else 0.0
    )
    task_consistency_percentage = (
        round(sum(consistency_percentages) / len(consistency_percentages), 1)
        if consistency_percentages
        else 0.0
    )

    overall_productivity = OverallProductivity(
        daily_trends=daily_trends,
        weekly_trends=weekly_trends,
        monthly_completion_percentage=monthly_completion_percentage,
        task_consistency_percentage=task_consistency_percentage,
    )

    return MonthlyReportRead(
        year=year,
        month=month,
        one_time_performance=one_time_performance,
        recurring_performance=recurring_performance,
        individual_task_performance=individual_task_performance,
        eisenhower_analysis=eisenhower_analysis,
        overall_productivity=overall_productivity,
    )
