"""
Integration tests for GET /api/dashboard.
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId

from src.config.db import get_db


def start_of_week_utc():
    now = datetime.now(timezone.utc)

    monday_date = (
        now.date()
        - timedelta(days=now.weekday())
    )

    return datetime.combine(
        monday_date,
        datetime.min.time(),
        tzinfo=timezone.utc
    )


def test_dashboard_empty_state(client):
    response = client.get(
        "/api/dashboard"
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["this_week"] == {
        "done": 0,
        "missed": 0,
        "streak": 0
    }

    assert len(
        data["daily_completion"]
    ) == 7

    assert data["priority_matrix"] == {
        "important_urgent": 0,
        "important_not_urgent": 0,
        "not_important_urgent": 0,
        "not_important_not_urgent": 0
    }

    assert data["insight"] is None


def test_dashboard_counts_done_missed_and_priorities(client):
    db = get_db()

    monday = start_of_week_utc()

    recurring_id = ObjectId()
    repeat_id = ObjectId()

    db.tasks.insert_many([
        {
            "_id": recurring_id,
            "task_type": "recurring",
            "title": "Morning exercise",
            "description": "",
            "priority": "important_urgent",
            "status": "active",
            "duration": {
                "start_date": monday.date().isoformat(),
                "end_date": (
                    monday.date()
                    + timedelta(days=30)
                ).isoformat()
            },
            "repeat": {
                "type": "everyday",
                "custom_dates": []
            },
            "reminders": [],
            "occurrence_count": 30,
            "created_at": monday,
            "updated_at": monday,
        },
        {
            "_id": repeat_id,
            "task_type": "repeat_until_done",
            "title": "Pay bill",
            "description": "",
            "priority": "important_not_urgent",
            "status": "pending",
            "created_at": monday,
            "updated_at": monday,
        }
    ])

    monday_str = monday.date().isoformat()
    tuesday_str = (
        monday.date()
        + timedelta(days=1)
    ).isoformat()

    db.task_occurrences.insert_many([
        {
            "task_id": recurring_id,
            "scheduled_date": monday_str,
            "status": "completed",
            "reminders": [],
            "reminders_cancelled": True,
            "completed_at": monday + timedelta(hours=8),
            "created_at": monday,
            "updated_at": monday,
        },
        {
            "task_id": recurring_id,
            "scheduled_date": tuesday_str,
            "status": "missed",
            "reminders": [],
            "reminders_cancelled": True,
            "completed_at": None,
            "created_at": monday,
            "updated_at": monday,
        }
    ])

    response = client.get(
        "/api/dashboard"
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["this_week"]["done"] == 1
    assert data["this_week"]["missed"] == 1

    assert (
        data["priority_matrix"]["important_urgent"]
        == 1
    )

    assert (
        data["priority_matrix"]["important_not_urgent"]
        == 1
    )


def test_dashboard_counts_completed_repeat_until_done(client):
    db = get_db()

    monday = start_of_week_utc()

    completed_at = monday + timedelta(
        hours=12
    )

    db.tasks.insert_one({
        "task_type": "repeat_until_done",
        "title": "Submit report",
        "description": "",
        "priority": "important_urgent",
        "status": "completed",
        "completed_at": completed_at,
        "created_at": monday,
        "updated_at": completed_at,
    })

    response = client.get(
        "/api/dashboard"
    )

    data = response.get_json()["data"]

    assert data["this_week"]["done"] == 1

    monday_point = data[
        "daily_completion"
    ][0]

    assert monday_point["completed"] == 1


def test_dashboard_builds_missed_weekday_insight(client):
    db = get_db()

    task_id = ObjectId()

    # A known Monday makes the expected weekday deterministic.
    first_monday = datetime(
        2026,
        9,
        7,
        tzinfo=timezone.utc
    )

    db.tasks.insert_one({
        "_id": task_id,
        "task_type": "recurring",
        "title": "Morning exercise",
        "description": "",
        "priority": "important_not_urgent",
        "status": "ended",
        "duration": {
            "start_date": "2026-09-01",
            "end_date": "2026-09-30"
        },
        "repeat": {
            "type": "weekdays",
            "custom_dates": []
        },
        "reminders": [],
        "occurrence_count": 20,
        "created_at": first_monday,
        "updated_at": first_monday,
        "ended_at": first_monday,
    })

    db.task_occurrences.insert_many([
        {
            "task_id": task_id,
            "scheduled_date": "2026-09-07",
            "status": "missed",
            "reminders": [],
            "reminders_cancelled": True,
            "completed_at": None,
            "created_at": first_monday,
            "updated_at": first_monday,
        },
        {
            "task_id": task_id,
            "scheduled_date": "2026-09-14",
            "status": "missed",
            "reminders": [],
            "reminders_cancelled": True,
            "completed_at": None,
            "created_at": first_monday,
            "updated_at": first_monday,
        }
    ])

    response = client.get(
        "/api/dashboard"
    )

    insight = response.get_json()[
        "data"
    ]["insight"]

    assert insight is not None
    assert insight["task_title"] == "Morning exercise"
    assert insight["weekday"] == "Monday"
    assert insight["missed_count"] == 2


def test_dashboard_streak_counts_successive_processed_days(client):
    db = get_db()

    task_id = ObjectId()
    today = datetime.now(
        timezone.utc
    ).date()

    days = [
        today - timedelta(days=2),
        today - timedelta(days=1),
        today,
    ]

    db.tasks.insert_one({
        "_id": task_id,
        "task_type": "recurring",
        "title": "Exercise",
        "description": "",
        "priority": "important_not_urgent",
        "status": "active",
        "duration": {
            "start_date": days[0].isoformat(),
            "end_date": (
                today
                + timedelta(days=30)
            ).isoformat()
        },
        "repeat": {
            "type": "everyday",
            "custom_dates": []
        },
        "reminders": [],
        "occurrence_count": 33,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    now = datetime.now(timezone.utc)

    db.task_occurrences.insert_many([
        {
            "task_id": task_id,
            "scheduled_date": day.isoformat(),
            "status": "completed",
            "reminders": [],
            "reminders_cancelled": True,
            "completed_at": now,
            "created_at": now,
            "updated_at": now,
        }
        for day in days
    ])

    response = client.get(
        "/api/dashboard"
    )

    assert response.get_json()[
        "data"
    ]["this_week"]["streak"] == 3
