"""
MongoDB queries used by the Dashboard feature.

The dashboard reads existing task data only. It does not create a new
dashboard collection.
"""

from src.config.db import get_db


def find_completed_recurring_occurrences_between(start_date, end_date):
    """
    Return recurring occurrences completed/scheduled inside the requested
    YYYY-MM-DD date range.

    We use scheduled_date for weekly dashboard grouping because the occurrence
    belongs to that calendar day even if the user completed it later that day.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "status": "completed",
            "scheduled_date": {
                "$gte": start_date,
                "$lte": end_date
            }
        })
    )


def find_missed_recurring_occurrences_between(start_date, end_date):
    """
    Return missed recurring occurrences inside a YYYY-MM-DD date range.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "status": "missed",
            "scheduled_date": {
                "$gte": start_date,
                "$lte": end_date
            }
        })
    )


def find_repeat_until_done_completed_between(start_datetime, end_datetime):
    """
    Return Repeat Until Done tasks completed inside a datetime range.

    Repeat Until Done has no "missed" state, so these tasks contribute only
    to completed dashboard statistics.
    """

    db = get_db()

    return list(
        db.tasks.find({
            "task_type": "repeat_until_done",
            "status": "completed",
            "completed_at": {
                "$gte": start_datetime,
                "$lte": end_datetime
            }
        })
    )


def find_active_dashboard_tasks():
    """
    Return active parent tasks used by the priority matrix.

    - Repeat Until Done: pending
    - Recurring: active
    """

    db = get_db()

    return list(
        db.tasks.find({
            "$or": [
                {
                    "task_type": "repeat_until_done",
                    "status": "pending"
                },
                {
                    "task_type": "recurring",
                    "status": "active"
                }
            ]
        })
    )


def find_all_missed_recurring_occurrences():
    """
    Return all missed recurring occurrences.

    The service joins these records with their recurring parent tasks to build
    the "most often missed" insight.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "status": "missed"
        })
    )


def find_recurring_tasks_by_ids(task_ids):
    """
    Return recurring parent tasks for the supplied ObjectIds.
    """

    if not task_ids:
        return []

    db = get_db()

    return list(
        db.tasks.find({
            "_id": {
                "$in": list(task_ids)
            },
            "task_type": "recurring"
        })
    )


def find_processed_recurring_occurrences_until(end_date):
    """
    Return completed/missed recurring occurrences through end_date.

    Used for the dashboard streak calculation.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "status": {
                "$in": [
                    "completed",
                    "missed"
                ]
            },
            "scheduled_date": {
                "$lte": end_date
            }
        })
    )
