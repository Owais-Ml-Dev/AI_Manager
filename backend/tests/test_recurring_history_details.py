"""
Tests for recurring task detail statistics and recurring history.

Copy this file into backend/tests/.
"""

from datetime import date, timedelta


def iso(day):
    return day.isoformat()


def test_recurring_details_returns_calendar_and_summary(client):
    today = date.today()
    future = today + timedelta(days=2)

    payload = {
        "title": "Morning exercise",
        "description": "Exercise during the recurring period",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(today),
            "end_date": iso(future)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(today),
                iso(future)
            ]
        },
        "reminders": []
    }

    created_response = client.post(
        "/api/tasks/recurring",
        json=payload
    )

    assert created_response.status_code == 201

    created = created_response.get_json()["data"]
    task_id = created["task"]["id"]

    today_occurrence = next(
        occurrence
        for occurrence in created["occurrences"]
        if occurrence["scheduled_date"] == iso(today)
    )

    complete_response = client.patch(
        "/api/tasks/recurring/occurrences/"
        f"{today_occurrence['id']}/complete"
    )

    assert complete_response.status_code == 200

    response = client.get(
        f"/api/tasks/recurring/{task_id}/details"
    )

    assert response.status_code == 200

    details = response.get_json()["data"]

    assert details["task"]["id"] == task_id
    assert details["task"]["status"] == "active"

    assert details["summary"] == {
        "done": 1,
        "missed": 0,
        "pending": 1,
        "processed": 1,
        "total": 2,
        "completion_rate": 100
    }

    assert details["today_occurrence"] is not None
    assert details["today_occurrence"]["status"] == "completed"
    assert details["today_occurrence"]["completed_at"] is not None

    assert len(details["occurrences"]) == 2


def test_recurring_details_marks_old_pending_occurrence_missed(client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    payload = {
        "title": "Daily reading",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(yesterday),
            "end_date": iso(tomorrow)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(yesterday),
                iso(today),
                iso(tomorrow)
            ]
        },
        "reminders": []
    }

    created = client.post(
        "/api/tasks/recurring",
        json=payload
    ).get_json()["data"]

    response = client.get(
        f"/api/tasks/recurring/"
        f"{created['task']['id']}/details"
    )

    assert response.status_code == 200

    details = response.get_json()["data"]

    assert details["summary"]["missed"] == 1
    assert details["summary"]["pending"] == 2
    assert details["summary"]["done"] == 0
    assert details["summary"]["completion_rate"] == 0


def test_recurring_history_returns_only_ended_tasks(client):
    today = date.today()

    past_start = today - timedelta(days=4)
    past_end = today - timedelta(days=2)

    expired_payload = {
        "title": "Finished exercise plan",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(past_start),
            "end_date": iso(past_end)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(past_start),
                iso(past_end)
            ]
        },
        "reminders": []
    }

    future_start = today + timedelta(days=2)
    future_end = today + timedelta(days=4)

    active_payload = {
        "title": "Active exercise plan",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(future_start),
            "end_date": iso(future_end)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(future_start),
                iso(future_end)
            ]
        },
        "reminders": []
    }

    expired = client.post(
        "/api/tasks/recurring",
        json=expired_payload
    )

    active = client.post(
        "/api/tasks/recurring",
        json=active_payload
    )

    assert expired.status_code == 201
    assert active.status_code == 201

    response = client.get(
        "/api/tasks/recurring/history"
    )

    assert response.status_code == 200

    history = response.get_json()

    assert history["count"] == 1

    item = history["data"][0]

    assert item["task"]["title"] == "Finished exercise plan"
    assert item["task"]["status"] == "ended"

    assert item["summary"]["done"] == 0
    assert item["summary"]["missed"] == 2
    assert item["summary"]["pending"] == 0
    assert item["summary"]["completion_rate"] == 0


def test_ended_recurring_task_details_are_still_available(client):
    today = date.today()

    start = today - timedelta(days=3)
    end = today - timedelta(days=1)

    payload = {
        "title": "Past recurring task",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(start),
            "end_date": iso(end)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(start),
                iso(end)
            ]
        },
        "reminders": []
    }

    created = client.post(
        "/api/tasks/recurring",
        json=payload
    ).get_json()["data"]

    task_id = created["task"]["id"]

    # History synchronization changes the parent to ended.
    history_response = client.get(
        "/api/tasks/recurring/history"
    )

    assert history_response.status_code == 200

    detail_response = client.get(
        f"/api/tasks/recurring/{task_id}/details"
    )

    assert detail_response.status_code == 200

    details = detail_response.get_json()["data"]

    assert details["task"]["status"] == "ended"
    assert details["summary"]["missed"] == 2
    assert len(details["occurrences"]) == 2


def test_recurring_details_invalid_id_returns_400(client):
    response = client.get(
        "/api/tasks/recurring/not-an-object-id/details"
    )

    assert response.status_code == 400


def test_recurring_details_missing_task_returns_404(client):
    response = client.get(
        "/api/tasks/recurring/"
        "507f1f77bcf86cd799439011/details"
    )

    assert response.status_code == 404
