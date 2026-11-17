"""Monthly productivity report. Read-only, computed fresh from existing
tasks/occurrences — nothing new persisted, no AI involved (Gemini must never
calculate these statistics, per spec).

Documented scoping policies (the spec leaves these to the implementer):
- One-time tasks are "in scope" for a month if their due_date falls within
  it. Tasks with no due_date aren't tied to any month and are excluded here.
  Classification (completed/overdue/remaining) uses the task's CURRENT
  status, and cancelled tasks are excluded entirely (from counts and the
  completion-rate denominator).
- Recurring occurrences are in scope if occurrence_date falls within the
  month. The completion rate excludes skipped occurrences and any occurrence
  whose date hasn't arrived yet (future pending), consistent with the same
  policy used by the dashboard and per-task analytics.
- The Eisenhower Matrix section is a live snapshot across all current tasks
  (quadrant membership isn't inherently date-bound), not filtered to the month.
- "Task consistency" = the average per-task completion percentage across all
  recurring tasks with at least one occurrence in the month.
"""
from datetime import date

from pydantic import BaseModel


class OneTimeMonthlyPerformance(BaseModel):
    completed: int
    overdue: int
    remaining: int
    completion_percentage: float


class RecurringMonthlyPerformance(BaseModel):
    scheduled_occurrences: int
    completed_occurrences: int
    missed_occurrences: int
    skipped_occurrences: int
    completion_rate: float


class IndividualTaskMonthlyPerformance(BaseModel):
    task_id: int
    title: str
    scheduled: int
    completed: int
    missed: int
    skipped: int
    completion_percentage: float


class QuadrantSummary(BaseModel):
    total: int
    completed: int
    pending: int


class EisenhowerMonthlyAnalysis(BaseModel):
    do_first: QuadrantSummary
    schedule: QuadrantSummary
    delegate: QuadrantSummary
    eliminate: QuadrantSummary


class DailyTrendPoint(BaseModel):
    date: date
    completed_count: int


class WeeklyTrendPoint(BaseModel):
    week_start: date
    week_end: date
    completed_count: int


class OverallProductivity(BaseModel):
    daily_trends: list[DailyTrendPoint]
    weekly_trends: list[WeeklyTrendPoint]
    monthly_completion_percentage: float
    task_consistency_percentage: float


class MonthlyReportRead(BaseModel):
    year: int
    month: int
    one_time_performance: OneTimeMonthlyPerformance
    recurring_performance: RecurringMonthlyPerformance
    individual_task_performance: list[IndividualTaskMonthlyPerformance]
    eisenhower_analysis: EisenhowerMonthlyAnalysis
    overall_productivity: OverallProductivity
