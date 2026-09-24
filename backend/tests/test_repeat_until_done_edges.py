"""
Additional edge-case tests for Repeat Until Done.
"""


def base_payload():
    return {
        "title": "Task",
        "description": "",
        "priority": "important_urgent",
        "duration": {"start_date": "2099-01-01", "end_date": "2099-12-31"},
        "repeat": {
            "type": "everyday",
            "custom_dates": []
        },
        "reminders": []
    }


def test_create_requires_body(client):
    response = client.post(
        "/api/tasks/repeat-until-done"
    )

    assert response.status_code == 400


def test_create_requires_title(client):
    payload = base_payload()
    payload.pop("title")

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400
    assert "title" in response.get_json()["errors"]


def test_description_must_be_string(client):
    payload = base_payload()
    payload["description"] = 123

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_invalid_repeat_type(client):
    payload = base_payload()
    payload["repeat"] = {
        "type": "sometimes",
        "custom_dates": []
    }

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_custom_dates_requires_at_least_one_date(client):
    payload = base_payload()
    payload["repeat"] = {
        "type": "custom_dates",
        "custom_dates": []
    }

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_non_custom_repeat_rejects_custom_dates(client):
    payload = base_payload()
    payload["repeat"] = {
        "type": "weekdays",
        "custom_dates": ["2099-01-01"]
    }

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_reminders_must_be_list(client):
    payload = base_payload()
    payload["reminders"] = {}

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_reminder_count_rejects_zero(client):
    payload = base_payload()
    payload["reminders"] = [
        {
            "start_time": "09:00",
            "end_time": "10:00",
            "count": 0
        }
    ]

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_update_requires_body(client):
    create = client.post(
        "/api/tasks/repeat-until-done",
        json=base_payload()
    ).get_json()["data"]

    response = client.patch(
        f"/api/tasks/repeat-until-done/{create['id']}"
    )

    assert response.status_code == 400


def test_update_rejects_protected_field(client):
    create = client.post(
        "/api/tasks/repeat-until-done",
        json=base_payload()
    ).get_json()["data"]

    response = client.patch(
        f"/api/tasks/repeat-until-done/{create['id']}",
        json={"status": "completed"}
    )

    assert response.status_code == 400


def test_get_nonexistent_repeat_until_done_returns_404(client):
    response = client.get(
        "/api/tasks/repeat-until-done/507f1f77bcf86cd799439011"
    )

    assert response.status_code == 404


def test_update_nonexistent_repeat_until_done_returns_404(client):
    response = client.patch(
        "/api/tasks/repeat-until-done/507f1f77bcf86cd799439011",
        json={"title": "Updated"}
    )

    assert response.status_code == 404


def test_complete_nonexistent_repeat_until_done_returns_404(client):
    response = client.patch(
        "/api/tasks/repeat-until-done/"
        "507f1f77bcf86cd799439011/complete"
    )

    assert response.status_code == 404


def test_delete_nonexistent_repeat_until_done_returns_404(client):
    response = client.delete(
        "/api/tasks/repeat-until-done/507f1f77bcf86cd799439011"
    )

    assert response.status_code == 404
