from datetime import date, timedelta

from bson import ObjectId

from src.config.db import get_db


def iso(day):
    return day.isoformat()


def future_custom_payload():
    today = date.today()

    d1 = today + timedelta(days=2)
    d2 = today + timedelta(days=4)
    d3 = today + timedelta(days=6)

    return {
        "title": "Go to the gym",
        "description": "Recurring gym task",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(d1),
            "end_date": iso(d3)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(d1),
                iso(d2),
                iso(d3)
            ]
        },
        "reminders": [
            {
                "start_time": "19:00",
                "end_time": "21:00",
                "count": 3
            }
        ]
    }


def create_recurring_task(client, payload=None):
    response = client.post(
        "/api/tasks/recurring",
        json=payload or future_custom_payload()
    )

    assert response.status_code == 201

    return response.get_json()["data"]


def test_create_recurring_parent_and_occurrences(client):
    result = create_recurring_task(client)

    assert result["task"]["task_type"] == "recurring"
    assert result["task"]["status"] == "active"
    assert result["task"]["occurrence_count"] == 3
    assert len(result["occurrences"]) == 3


def test_get_all_recurring_tasks(client):
    result = create_recurring_task(client)

    response = client.get(
        "/api/tasks/recurring"
    )

    assert response.status_code == 200
    assert response.get_json()["count"] == 1


def test_get_one_recurring_task(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]

    response = client.get(
        f"/api/tasks/recurring/{task_id}"
    )

    assert response.status_code == 200


def test_get_recurring_occurrences(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]

    response = client.get(
        f"/api/tasks/recurring/{task_id}/occurrences"
    )

    assert response.status_code == 200
    assert response.get_json()["count"] == 3


def test_complete_only_one_occurrence(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]
    occurrence_id = result["occurrences"][0]["id"]

    response = client.patch(
        f"/api/tasks/recurring/occurrences/{occurrence_id}/complete"
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "completed"

    occurrences = client.get(
        f"/api/tasks/recurring/{task_id}/occurrences"
    ).get_json()["data"]

    statuses = [x["status"] for x in occurrences]

    assert statuses.count("completed") == 1
    assert statuses.count("pending") == 2


def test_recurring_occurrence_cannot_be_completed_twice(client):
    result = create_recurring_task(client)

    occurrence_id = result["occurrences"][0]["id"]

    assert client.patch(
        f"/api/tasks/recurring/occurrences/{occurrence_id}/complete"
    ).status_code == 200

    assert client.patch(
        f"/api/tasks/recurring/occurrences/{occurrence_id}/complete"
    ).status_code == 409


def test_update_recurring_reminders_updates_pending_occurrences(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]

    response = client.patch(
        f"/api/tasks/recurring/{task_id}",
        json={
            "reminders": [
                {
                    "start_time": "18:00",
                    "end_time": "20:00",
                    "count": 3
                }
            ]
        }
    )

    assert response.status_code == 200


def test_schedule_update_preserves_completed_occurrence(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]
    completed_occurrence = result["occurrences"][0]

    client.patch(
        "/api/tasks/recurring/occurrences/"
        f"{completed_occurrence['id']}/complete"
    )

    today = date.today()

    new_1 = today + timedelta(days=8)
    new_2 = today + timedelta(days=10)

    response = client.patch(
        f"/api/tasks/recurring/{task_id}",
        json={
            "duration": {
                "start_date": iso(new_1),
                "end_date": iso(new_2)
            },
            "repeat": {
                "type": "custom_dates",
                "custom_dates": [
                    iso(new_1),
                    iso(new_2)
                ]
            }
        }
    )

    assert response.status_code == 200


def test_recurring_custom_date_outside_duration_rejected(client):
    today = date.today()

    payload = future_custom_payload()

    payload["duration"] = {
        "start_date": iso(today + timedelta(days=2)),
        "end_date": iso(today + timedelta(days=5))
    }

    payload["repeat"] = {
        "type": "custom_dates",
        "custom_dates": [
            iso(today + timedelta(days=10))
        ]
    }

    assert client.post(
        "/api/tasks/recurring",
        json=payload
    ).status_code == 400


def test_recurring_invalid_duration_rejected(client):
    payload = future_custom_payload()

    payload["duration"] = {
        "start_date": "2099-10-10",
        "end_date": "2099-09-10"
    }

    assert client.post(
        "/api/tasks/recurring",
        json=payload
    ).status_code == 400


def test_delete_recurring_removes_parent_and_occurrences(client):
    result = create_recurring_task(client)

    task_id = result["task"]["id"]

    assert client.delete(
        f"/api/tasks/recurring/{task_id}"
    ).status_code == 200

    db = get_db()

    assert db.tasks.count_documents({
        "_id": ObjectId(task_id)
    }) == 0

    assert db.task_occurrences.count_documents({
        "task_id": ObjectId(task_id)
    }) == 0


def test_past_pending_occurrences_become_missed(client):
    today = date.today()

    d1 = today - timedelta(days=4)
    d2 = today - timedelta(days=3)
    d3 = today - timedelta(days=2)

    payload = {
        "title": "Past recurring task",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(d1),
            "end_date": iso(d3)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(d1),
                iso(d2),
                iso(d3)
            ]
        },
        "reminders": []
    }

    result = create_recurring_task(client, payload)

    response = client.get(
        f"/api/tasks/recurring/"
        f"{result['task']['id']}/occurrences"
    )

    occurrences = response.get_json()["data"]

    assert all(x["status"] == "missed" for x in occurrences)


def test_expired_recurring_parent_becomes_ended(client):
    today = date.today()

    d1 = today - timedelta(days=3)
    d2 = today - timedelta(days=1)

    payload = {
        "title": "Expired recurring task",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": iso(d1),
            "end_date": iso(d2)
        },
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                iso(d1),
                iso(d2)
            ]
        },
        "reminders": []
    }

    result = create_recurring_task(client, payload)

    response = client.get(
        f"/api/tasks/recurring/{result['task']['id']}"
    )

    task = response.get_json()["data"]

    assert task["status"] == "ended"
    assert task["ended_at"] is not None


def test_invalid_recurring_object_id_returns_400(client):
    assert client.get(
        "/api/tasks/recurring/not-an-object-id"
    ).status_code == 400



def test_complete_recurring_task_permanently(
    client,
):
    payload = {
        "title": "Permanent recurring test",
        "description": "",
        "priority": "important_not_urgent",
        "duration": {
            "start_date": "2099-01-01",
            "end_date": "2099-01-05"
        },
        "repeat": {
            "type": "everyday",
            "custom_dates": []
        },
        "reminders": []
    }

    created = client.post(
        "/api/tasks/recurring",
        json=payload
    )

    assert created.status_code == 201

    task_id = (
        created.get_json()
        ["data"]
        ["task"]
        ["id"]
    )

    response = client.patch(
        f"/api/tasks/recurring/"
        f"{task_id}/complete"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["success"] is True
    assert data["data"]["status"] == "ended"

    active = client.get(
        "/api/tasks/recurring"
    ).get_json()["data"]

    assert not any(
        task["id"] == task_id
        for task in active
    )

    history = client.get(
        "/api/tasks/recurring/history"
    ).get_json()["data"]

    assert any(
        item["task"]["id"] == task_id
        for item in history
    )

    occurrences = client.get(
        f"/api/tasks/recurring/"
        f"{task_id}/occurrences"
    ).get_json()["data"]

    assert not any(
        occurrence["status"] == "pending"
        for occurrence in occurrences
    )
