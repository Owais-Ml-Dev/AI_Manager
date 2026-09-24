"""
Additional edge-case and controller tests for Recurring.
"""

from datetime import date, timedelta


def iso(day):
    return day.isoformat()


def payload():
    today = date.today()

    start = today + timedelta(days=2)
    end = today + timedelta(days=6)

    return {
        "title": "Gym",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(start),
            "end_date": iso(end)
        },
        "repeat": {
            "type": "weekdays",
            "custom_dates": []
        },
        "reminders": []
    }


def create(client):
    response = client.post(
        "/api/tasks/recurring",
        json=payload()
    )

    assert response.status_code == 201

    return response.get_json()["data"]


def test_recurring_create_requires_body(client):
    assert client.post(
        "/api/tasks/recurring"
    ).status_code == 400


def test_recurring_create_requires_title(client):
    p = payload()
    p.pop("title")

    response = client.post(
        "/api/tasks/recurring",
        json=p
    )

    assert response.status_code == 400


def test_recurring_description_must_be_string(client):
    p = payload()
    p["description"] = 123

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_invalid_priority(client):
    p = payload()
    p["priority"] = "wrong"

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_requires_duration(client):
    p = payload()
    p.pop("duration")

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_invalid_start_date(client):
    p = payload()
    p["duration"]["start_date"] = "bad-date"

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_invalid_end_date(client):
    p = payload()
    p["duration"]["end_date"] = "bad-date"

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_requires_repeat(client):
    p = payload()
    p.pop("repeat")

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_invalid_repeat_type(client):
    p = payload()
    p["repeat"] = {
        "type": "sometimes",
        "custom_dates": []
    }

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_custom_dates_requires_list(client):
    p = payload()
    p["repeat"] = {
        "type": "custom_dates",
        "custom_dates": "not-a-list"
    }

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_custom_dates_cannot_be_empty(client):
    p = payload()
    p["repeat"] = {
        "type": "custom_dates",
        "custom_dates": []
    }

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_duplicate_custom_dates(client):
    p = payload()

    d = p["duration"]["start_date"]

    p["repeat"] = {
        "type": "custom_dates",
        "custom_dates": [d, d]
    }

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_non_custom_rejects_custom_dates(client):
    p = payload()
    p["repeat"] = {
        "type": "weekends",
        "custom_dates": [
            p["duration"]["start_date"]
        ]
    }

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_reminders_must_be_list(client):
    p = payload()
    p["reminders"] = {}

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_invalid_reminder_count(client):
    p = payload()
    p["reminders"] = [
        {
            "start_time": "09:00",
            "end_time": "10:00",
            "count": 0
        }
    ]

    assert client.post(
        "/api/tasks/recurring",
        json=p
    ).status_code == 400


def test_recurring_update_requires_body(client):
    created = create(client)

    task_id = created["task"]["id"]

    assert client.patch(
        f"/api/tasks/recurring/{task_id}"
    ).status_code == 400


def test_recurring_update_rejects_protected_field(client):
    created = create(client)

    task_id = created["task"]["id"]

    assert client.patch(
        f"/api/tasks/recurring/{task_id}",
        json={"status": "ended"}
    ).status_code == 400


def test_recurring_get_nonexistent_returns_404(client):
    assert client.get(
        "/api/tasks/recurring/507f1f77bcf86cd799439011"
    ).status_code == 404


def test_recurring_update_nonexistent_returns_404(client):
    assert client.patch(
        "/api/tasks/recurring/507f1f77bcf86cd799439011",
        json={"title": "Changed"}
    ).status_code == 404


def test_recurring_delete_nonexistent_returns_404(client):
    assert client.delete(
        "/api/tasks/recurring/507f1f77bcf86cd799439011"
    ).status_code == 404


def test_get_occurrences_nonexistent_parent_returns_404(client):
    assert client.get(
        "/api/tasks/recurring/"
        "507f1f77bcf86cd799439011/occurrences"
    ).status_code == 404


def test_get_nonexistent_occurrence_returns_404(client):
    assert client.get(
        "/api/tasks/recurring/occurrences/"
        "507f1f77bcf86cd799439011"
    ).status_code == 404


def test_complete_nonexistent_occurrence_returns_404(client):
    assert client.patch(
        "/api/tasks/recurring/occurrences/"
        "507f1f77bcf86cd799439011/complete"
    ).status_code == 404
