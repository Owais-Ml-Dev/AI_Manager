"""
Dashboard business logic.

Dashboard semantics used here:

1. "Done this week"
   - completed recurring occurrences scheduled this week
   - Repeat Until Done tasks completed this week

2. "Missed this week"
   - missed recurring occurrences scheduled this week
   - Repeat Until Done does not have a missed state

3. "Streak"
   - consecutive scheduled recurring days, ending today or the most recent
     processed scheduled day, where every processed recurring occurrence on
     that date was completed and none were missed
   - days with no processed recurring occurrence do not create a streak day

4. Priority matrix
   - current active parent tasks only

5. Insight
   - most common (recurring task, weekday) combination among missed
     occurrences
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from src.modules.dashboard.repository import (
    find_active_dashboard_tasks,
    find_all_missed_recurring_occurrences,
    find_completed_recurring_occurrences_between,
    find_missed_recurring_occurrences_between,
    find_processed_recurring_occurrences_until,
    find_recurring_tasks_by_ids,
    find_repeat_until_done_completed_between,
)


PRIORITY_KEYS = (
    "important_urgent",
    "important_not_urgent",
    "not_important_urgent",
    "not_important_not_urgent",
)


def _utc_now():
    """
    Small wrapper to keep date/time logic easy to test.
    """
    return datetime.now(timezone.utc)


def _week_bounds(now):
    """
    Return Monday 00:00 through Sunday 23:59:59.999999 in UTC,
    plus YYYY-MM-DD strings for occurrence queries.
    """

    monday_date = now.date() - timedelta(days=now.weekday())
    sunday_date = monday_date + timedelta(days=6)

    start_datetime = datetime.combine(
        monday_date,
        datetime.min.time(),
        tzinfo=timezone.utc
    )

    end_datetime = datetime.combine(
        sunday_date,
        datetime.max.time(),
        tzinfo=timezone.utc
    )

    return {
        "start_date": monday_date.isoformat(),
        "end_date": sunday_date.isoformat(),
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
    }


def _build_daily_completion(
    start_date,
    completed_occurrences,
    completed_repeat_tasks,
):
    """
    Build seven daily chart points starting on Monday.
    """

    monday = datetime.fromisoformat(
        start_date
    ).date()

    counts = Counter()

    for occurrence in completed_occurrences:
        counts[occurrence["scheduled_date"]] += 1

    for task in completed_repeat_tasks:
        completed_at = task.get("completed_at")

        if completed_at is not None:
            counts[completed_at.date().isoformat()] += 1

    result = []

    for offset in range(7):
        current_date = monday + timedelta(days=offset)
        date_string = current_date.isoformat()

        result.append({
            "date": date_string,
            "day": current_date.strftime("%a"),
            "completed": counts[date_string],
        })

    return result


def _build_priority_matrix(active_tasks):
    """
    Count currently active parent tasks by the four priority matrix values.
    """

    matrix = {
        key: 0
        for key in PRIORITY_KEYS
    }

    for task in active_tasks:
        priority = task.get("priority")

        if priority in matrix:
            matrix[priority] += 1

    return matrix


def _build_streak(processed_occurrences):
    """
    Calculate a recurring completion streak.

    A date is successful when:
        - at least one recurring occurrence was processed on that date
        - every processed occurrence on that date is completed
        - none is missed

    We count consecutive *processed recurring dates*. This avoids breaking a
    streak simply because a user had no recurring task scheduled on a day.
    """

    by_date = defaultdict(list)

    for occurrence in processed_occurrences:
        by_date[occurrence["scheduled_date"]].append(
            occurrence.get("status")
        )

    successful_dates = []

    for scheduled_date, statuses in by_date.items():
        if statuses and all(
            status == "completed"
            for status in statuses
        ):
            successful_dates.append(scheduled_date)

    if not successful_dates:
        return 0

    successful_dates = sorted(
        set(successful_dates)
    )

    processed_dates = sorted(
        set(by_date.keys())
    )

    # Start with the latest processed recurring date. This lets a user keep a
    # streak when today has no scheduled recurring occurrence yet.
    latest_processed_date = processed_dates[-1]

    if latest_processed_date not in successful_dates:
        return 0

    streak = 1
    latest_index = processed_dates.index(
        latest_processed_date
    )

    for index in range(
        latest_index - 1,
        -1,
        -1
    ):
        current_processed_date = processed_dates[index]

        if current_processed_date in successful_dates:
            streak += 1
        else:
            break

    return streak


def _build_missed_insight(missed_occurrences, recurring_tasks):
    """
    Find the most frequently missed recurring task + weekday pair.
    """

    if not missed_occurrences:
        return None

    task_lookup = {
        task["_id"]: task
        for task in recurring_tasks
    }

    pair_counter = Counter()

    for occurrence in missed_occurrences:
        task = task_lookup.get(
            occurrence.get("task_id")
        )

        if task is None:
            continue

        scheduled_date = datetime.fromisoformat(
            occurrence["scheduled_date"]
        ).date()

        weekday = scheduled_date.strftime("%A")

        pair_counter[
            (
                occurrence["task_id"],
                weekday
            )
        ] += 1

    if not pair_counter:
        return None

    (
        task_id,
        weekday
    ), count = pair_counter.most_common(1)[0]

    task = task_lookup[task_id]

    return {
        "type": "most_missed_recurring_day",
        "task_id": str(task_id),
        "task_title": task.get("title", ""),
        "weekday": weekday,
        "missed_count": count,
        "message": (
            f"You miss {task.get('title', 'this task')} "
            f"most often on {weekday}s."
        ),
    }


def get_dashboard():
    """
    Build the complete Dashboard payload used by the Flutter dashboard screen.
    """

    now = _utc_now()
    bounds = _week_bounds(now)

    completed_occurrences = (
        find_completed_recurring_occurrences_between(
            bounds["start_date"],
            bounds["end_date"]
        )
    )

    missed_occurrences_this_week = (
        find_missed_recurring_occurrences_between(
            bounds["start_date"],
            bounds["end_date"]
        )
    )

    completed_repeat_tasks = (
        find_repeat_until_done_completed_between(
            bounds["start_datetime"],
            bounds["end_datetime"]
        )
    )

    active_tasks = find_active_dashboard_tasks()

    all_missed_occurrences = (
        find_all_missed_recurring_occurrences()
    )

    missed_task_ids = {
        occurrence["task_id"]
        for occurrence in all_missed_occurrences
        if occurrence.get("task_id") is not None
    }

    recurring_tasks = find_recurring_tasks_by_ids(
        missed_task_ids
    )

    processed_occurrences = (
        find_processed_recurring_occurrences_until(
            now.date().isoformat()
        )
    )

    done_count = (
        len(completed_occurrences)
        + len(completed_repeat_tasks)
    )

    missed_count = len(
        missed_occurrences_this_week
    )

    return {
        "week": {
            "start_date": bounds["start_date"],
            "end_date": bounds["end_date"],
        },
        "this_week": {
            "done": done_count,
            "missed": missed_count,
            "streak": _build_streak(
                processed_occurrences
            ),
        },
        "daily_completion": _build_daily_completion(
            bounds["start_date"],
            completed_occurrences,
            completed_repeat_tasks,
        ),
        "priority_matrix": _build_priority_matrix(
            active_tasks
        ),
        "insight": _build_missed_insight(
            all_missed_occurrences,
            recurring_tasks,
        ),
    }
