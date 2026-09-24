"""Tests for server-owned assistant drafts and deterministic execution.

These tests never call Gemini.
"""

from datetime import datetime, timedelta, timezone

from src.config.db import get_db
from src.modules.assistant import controller
from src.modules.assistant.draft_validation import build_preview
from src.modules.assistant.duplicate_matcher import find_create_duplicates


def repeat_task_payload(title="Pay electricity bill"):
    return {
        "title": title,
        "description": "",
        "priority": "important_urgent",
        "duration": {"start_date": "2099-01-01", "end_date": "2099-12-31"},
        "repeat": {"type": "everyday", "custom_dates": []},
        "reminders": [
            {
                "start_time": "19:00",
                "end_time": "19:01",
                "count": 1,
            }
        ],
    }


def _insert_draft(command, status="ready", duplicate_matches=None):
    now = datetime.now(timezone.utc)
    result = get_db().assistant_drafts.insert_one(
        {
            "status": status,
            "intent": {},
            "command": command,
            "duplicate_matches": duplicate_matches or [],
            "target_matches": [],
            "question": None,
            "missing_fields": [],
            "validation_errors": {},
            "provider": "gemini",
            "model": "gemini-test",
            "timezone": "UTC",
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(hours=1),
            "executed_at": None,
            "result": None,
        }
    )
    return str(result.inserted_id)


def test_task_command_preview_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        controller,
        "preview_task_command",
        lambda **kwargs: {
            "provider": "gemini",
            "model": "gemini-test",
            "timezone": "Asia/Kolkata",
            "draft_id": "draft-test",
            "status": "ready",
            "question": None,
            "missing_fields": [],
            "validation_errors": {},
            "duplicate_matches": [],
            "target_matches": [],
            "command": {
                "action": "create_repeat_until_done_task",
                "arguments": {"task": repeat_task_payload()},
                "summary": "Create Pay electricity bill.",
                "requires_confirmation": True,
            },
        },
    )

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message": "Remind me to pay the electricity bill.",
            "timezone": "Asia/Kolkata",
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["draft_id"] == "draft-test"
    assert data["command"]["requires_confirmation"] is True


def test_task_command_preview_rejects_bad_timezone(client):
    response = client.post(
        "/api/assistant/task-command/preview",
        json={"message": "Show my tasks.", "timezone": 123},
    )
    assert response.status_code == 400


def test_backend_not_gemini_decides_missing_fields():
    preview = build_preview(
        {
            "action": "create_recurring_task",
            "arguments": {
                "task": {
                    "title": "Study",
                    "repeat": {"type": "everyday", "custom_dates": []},
                }
            },
        }
    )

    # Task type must be explicitly confirmed before collecting
    # the remaining task details. Gemini's create action is only
    # treated as a provisional classification.
    assert preview["status"] == "needs_input"
    assert preview["missing_fields"] == ["task_type"]


def test_execute_create_requires_confirmation(client):
    command = {
        "action": "create_repeat_until_done_task",
        "arguments": {"task": repeat_task_payload()},
        "summary": "Create bill task.",
        "requires_confirmation": True,
    }
    draft_id = _insert_draft(command)

    response = client.post(
        "/api/assistant/task-command/execute",
        json={"draft_id": draft_id, "confirmed": False},
    )
    assert response.status_code == 409


def test_execute_create_repeat_until_done_once(client):
    command = {
        "action": "create_repeat_until_done_task",
        "arguments": {"task": repeat_task_payload()},
        "summary": "Create bill task.",
        "requires_confirmation": True,
    }
    draft_id = _insert_draft(command)

    first = client.post(
        "/api/assistant/task-command/execute",
        json={"draft_id": draft_id, "confirmed": True},
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["result"]["task_type"] == "repeat_until_done"

    second = client.post(
        "/api/assistant/task-command/execute",
        json={"draft_id": draft_id, "confirmed": True},
    )
    assert second.status_code == 409
    assert get_db().tasks.count_documents({"title": "Pay electricity bill"}) == 1


def test_execute_list_active_tasks_does_not_need_confirmation(client):
    client.post("/api/tasks/repeat-until-done", json=repeat_task_payload())
    command = {
        "action": "list_active_tasks",
        "arguments": {},
        "summary": "List active tasks.",
        "requires_confirmation": False,
    }
    draft_id = _insert_draft(command)

    response = client.post(
        "/api/assistant/task-command/execute",
        json={"draft_id": draft_id, "confirmed": False},
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert len(result["repeat_until_done"]) == 1


def test_execute_complete_repeat_until_done(client):
    created = client.post(
        "/api/tasks/repeat-until-done", json=repeat_task_payload()
    ).get_json()["data"]

    command = {
        "action": "complete_repeat_until_done_task",
        "arguments": {"task_id": created["id"]},
        "summary": "Complete bill task.",
        "requires_confirmation": True,
    }
    draft_id = _insert_draft(command)

    response = client.post(
        "/api/assistant/task-command/execute",
        json={"draft_id": draft_id, "confirmed": True},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["result"]["status"] == "completed"


def test_duplicate_matcher_uses_backend_tasks(client):
    client.post(
        "/api/tasks/repeat-until-done",
        json=repeat_task_payload("Drink water"),
    )

    command = {
        "action": "create_repeat_until_done_task",
        "arguments": {"task": repeat_task_payload("Drink water daily")},
        "summary": "Create Drink water daily.",
        "requires_confirmation": True,
    }

    matches = find_create_duplicates(command)
    assert matches
    assert matches[0]["title"] == "Drink water"
