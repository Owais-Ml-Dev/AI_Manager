"""Step 1G: HTTP API for the ordered multi-task batch workflow."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant import controller


def _intent(title):
    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": {"title": title},
            "collect": {
                "task_type_confirmed": True,
                "selected_task_action": "create_recurring_task",
            },
        },
    }


def _parsed():
    return {
        "provider": "groq",
        "type": "api",
        "model": "test-model",
        "timezone": "UTC",
        "intents": [
            _intent("Gym"),
            _intent("Call John"),
        ],
        "task_count": 2,
        "fallback_used": False,
        "attempted_providers": ["groq"],
    }


def _start(client, monkeypatch):
    monkeypatch.setattr(
        controller,
        "parse_task_batch_message",
        lambda **kwargs: _parsed(),
    )

    response = client.post(
        "/api/assistant/task-batch/start",
        json={
            "message": "Create Gym and Call John.",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def _continue_first_to_review(client, batch_id):
    answers = [
        "1 Jan 2099 to 31 Jan 2099",
        "Every day",
        "1",
        "7 am to 8 am",
        "2",
    ]

    data = None
    for answer in answers:
        response = client.post(
            f"/api/assistant/task-batch/{batch_id}/continue",
            json={"message": answer},
        )
        assert response.status_code == 200
        data = response.get_json()["data"]

    return data


def test_batch_start_requires_message(client):
    response = client.post(
        "/api/assistant/task-batch/start",
        json={"message": "   "},
    )
    assert response.status_code == 400


def test_batch_start_creates_batch_and_prepares_only_task_one(
    client,
    monkeypatch,
):
    data = _start(client, monkeypatch)

    assert data["total_tasks"] == 2
    assert data["current_task_number"] == 1
    assert data["items"][0]["status"] == "active"
    assert data["items"][1]["status"] == "pending"
    assert data["active_task"]["draft"]["status"] == "needs_input"
    assert data["active_task"]["draft"]["missing_fields"] == ["duration"]

    assert get_db().assistant_task_batches.count_documents({}) == 1
    assert get_db().assistant_drafts.count_documents({}) == 1
    assert get_db().tasks.count_documents({}) == 0


def test_active_endpoint_reuses_the_same_task_one_draft(client, monkeypatch):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    original_draft = started["active_task"]["draft"]["draft_id"]

    response = client.get(
        f"/api/assistant/task-batch/{batch_id}/active"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["draft"]["draft_id"] == original_draft
    assert get_db().assistant_drafts.count_documents({}) == 1


def test_continue_endpoint_moves_task_one_to_review(client, monkeypatch):
    started = _start(client, monkeypatch)
    data = _continue_first_to_review(client, started["batch_id"])

    assert data["current_task_number"] == 1
    assert data["draft"]["status"] in {"ready", "duplicate_review"}
    assert data["draft"]["command"]["requires_confirmation"] is True
    assert get_db().tasks.count_documents({}) == 0


def test_confirm_endpoint_executes_task_one_and_prepares_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    ready = _continue_first_to_review(client, batch_id)

    response = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": ready["draft"]["draft_id"]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolution"] == "executed"
    assert data["resolved_task_number"] == 1
    assert data["current_task_number"] == 2
    assert data["next_task"]["draft"]["status"] == "needs_input"
    assert get_db().tasks.count_documents({"title": "Gym"}) == 1
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0


def test_cancel_endpoint_skips_task_one_and_prepares_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    draft_id = started["active_task"]["draft"]["draft_id"]

    response = client.post(
        f"/api/assistant/task-batch/{batch_id}/cancel",
        json={"draft_id": draft_id},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolution"] == "skipped"
    assert data["resolved_task_number"] == 1
    assert data["current_task_number"] == 2
    assert data["next_task"] is not None
    assert get_db().tasks.count_documents({}) == 0


def test_stale_task_one_confirmation_cannot_confirm_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    ready = _continue_first_to_review(client, batch_id)
    stale_draft_id = ready["draft"]["draft_id"]

    first = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": stale_draft_id},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": stale_draft_id},
    )

    assert second.status_code == 409
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0
