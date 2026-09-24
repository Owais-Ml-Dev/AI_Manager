def valid_payload():
    return {
        "title": "Pay electricity bill",
        "description": "Keep reminding until completed",
        "priority": "important_urgent",
        "duration": {"start_date": "2099-09-01", "end_date": "2099-09-30"},
        "repeat": {
            "type": "custom_dates",
            "custom_dates": [
                "2099-09-20",
                "2099-09-25"
            ]
        },
        "reminders": [
            {
                "start_time": "09:00",
                "end_time": "10:00",
                "count": 3
            }
        ]
    }


def create_task(client, payload=None):
    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload or valid_payload()
    )

    assert response.status_code == 201

    return response.get_json()["data"]


def test_create_repeat_until_done_task(client):
    task = create_task(client)

    assert task["task_type"] == "repeat_until_done"
    assert task["status"] == "pending"
    assert task["reminders_cancelled"] is False


def test_get_active_repeat_until_done_tasks(client):
    created = create_task(client)

    response = client.get(
        "/api/tasks/repeat-until-done"
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["count"] == 1
    assert body["data"][0]["id"] == created["id"]


def test_get_repeat_until_done_task_by_id(client):
    created = create_task(client)

    response = client.get(
        f"/api/tasks/repeat-until-done/{created['id']}"
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["id"] == created["id"]


def test_update_pending_repeat_until_done_task(client):
    created = create_task(client)

    response = client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}",
        json={
            "priority": "important_not_urgent",
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

    task = response.get_json()["data"]

    assert task["priority"] == "important_not_urgent"
    assert task["reminders"][0]["generated_times"] == [
        "18:00",
        "19:00",
        "20:00"
    ]


def test_complete_repeat_until_done_task(client):
    created = create_task(client)

    response = client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}/complete"
    )

    assert response.status_code == 200

    task = response.get_json()["data"]

    assert task["status"] == "completed"
    assert task["completed_at"] is not None
    assert task["reminders_cancelled"] is True


def test_completed_task_moves_from_active_to_history(client):
    created = create_task(client)

    client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}/complete"
    )

    active = client.get(
        "/api/tasks/repeat-until-done"
    ).get_json()

    history = client.get(
        "/api/tasks/repeat-until-done/history"
    ).get_json()

    assert active["count"] == 0
    assert history["count"] == 1


def test_completed_repeat_until_done_cannot_be_edited(client):
    created = create_task(client)

    client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}/complete"
    )

    response = client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}",
        json={"title": "Changed"}
    )

    assert response.status_code == 409


def test_repeat_until_done_cannot_be_completed_twice(client):
    created = create_task(client)

    assert client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}/complete"
    ).status_code == 200

    assert client.patch(
        f"/api/tasks/repeat-until-done/{created['id']}/complete"
    ).status_code == 409


def test_delete_repeat_until_done_task(client):
    created = create_task(client)

    response = client.delete(
        f"/api/tasks/repeat-until-done/{created['id']}"
    )

    assert response.status_code == 200


def test_repeat_until_done_rejects_invalid_priority(client):
    payload = valid_payload()
    payload["priority"] = "wrong_priority"

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_repeat_until_done_rejects_invalid_custom_date(client):
    payload = valid_payload()
    payload["repeat"] = {
        "type": "custom_dates",
        "custom_dates": ["2099-02-30"]
    }

    response = client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    )

    assert response.status_code == 400


def test_repeat_until_done_rejects_duplicate_custom_dates(client):
    payload = valid_payload()
    payload["repeat"] = {
        "type": "custom_dates",
        "custom_dates": [
            "2099-09-20",
            "2099-09-20"
        ]
    }

    assert client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    ).status_code == 400


def test_repeat_until_done_rejects_invalid_reminder_window(client):
    payload = valid_payload()
    payload["reminders"] = [
        {
            "start_time": "20:00",
            "end_time": "18:00",
            "count": 2
        }
    ]

    assert client.post(
        "/api/tasks/repeat-until-done",
        json=payload
    ).status_code == 400


def test_repeat_until_done_invalid_object_id_returns_400(client):
    assert client.get(
        "/api/tasks/repeat-until-done/not-an-object-id"
    ).status_code == 400
