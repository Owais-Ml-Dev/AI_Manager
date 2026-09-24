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


def test_execute_delete_repeat_until_done_requires_confirmation(
    client,
    monkeypatch,
):
    db = get_db()
    """
    Delete through Assistant must:
    1. resolve the existing task,
    2. require confirmation,
    3. delete only after confirmed=true.
    """

    from datetime import datetime, timezone

    task_id = db.tasks.insert_one(
        {
            "task_type": "repeat_until_done",
            "title": "Swimming",
            "description": "Swimming task",
            "priority": "not_important_not_urgent",
            "duration": {
                "start_date": "2026-09-24",
                "end_date": "2026-10-24",
            },
            "repeat": {
                "type": "everyday",
                "custom_dates": [],
            },
            "reminders": [
                {
                    "start_time": "15:40",
                    "end_time": "15:50",
                    "count": 3,
                    "generated_times": [
                        "15:40",
                        "15:45",
                        "15:50",
                    ],
                }
            ],
            "status": "pending",
            "reminders_cancelled": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ).inserted_id

    monkeypatch.setattr(
        "src.modules.assistant.drafts.service.parse_task_message",
        lambda **kwargs: {
            "provider": "gemini",
            "model": "test-model",
            "intent": {
                "action": "delete_task",
                "arguments": {
                    "target_text": "Swimming"
                },
            },
        },
    )

    preview_response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message": "Delete swimming task",
            "timezone": "+05:30",
        },
        headers={
            "X-Gemini-Api-Key": "test-key",
        },
    )

    assert preview_response.status_code == 200

    preview = preview_response.get_json()["data"]

    assert preview["status"] == "ready"
    assert (
        preview["command"]["action"]
        == "delete_repeat_until_done_task"
    )

    draft_id = preview["draft_id"]

    # --------------------------------------------------
    # NOT CONFIRMED -> MUST NOT DELETE
    # --------------------------------------------------

    response = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id": draft_id,
            "confirmed": False,
        },
    )

    assert response.status_code == 409

    assert (
        db.tasks.find_one(
            {"_id": task_id}
        )
        is not None
    )

    # --------------------------------------------------
    # CONFIRMED -> DELETE
    # --------------------------------------------------

    response = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id": draft_id,
            "confirmed": True,
        },
    )

    assert response.status_code == 200

    assert (
        db.tasks.find_one(
            {"_id": task_id}
        )
        is None
    )


def test_execute_delete_recurring_removes_occurrences(
    client,
    monkeypatch,
):
    db = get_db()
    """
    Deleting a recurring task through Assistant must also
    delete its occurrence documents.
    """

    from datetime import datetime, timezone

    task_id = db.tasks.insert_one(
        {
            "task_type": "recurring",
            "title": "Morning Exercise",
            "description": "Exercise every morning",
            "priority": "important_not_urgent",
            "duration": {
                "start_date": "2026-09-24",
                "end_date": "2026-10-24",
            },
            "repeat": {
                "type": "everyday",
                "custom_dates": [],
            },
            "reminders": [
                {
                    "start_time": "07:00",
                    "end_time": "08:00",
                    "count": 1,
                    "generated_times": [
                        "07:00"
                    ],
                }
            ],
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ).inserted_id

    occurrence_id = db.task_occurrences.insert_one(
        {
            "task_id": task_id,
            "scheduled_date": "2026-09-24",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ).inserted_id

    monkeypatch.setattr(
        "src.modules.assistant.drafts.service.parse_task_message",
        lambda **kwargs: {
            "provider": "gemini",
            "model": "test-model",
            "intent": {
                "action": "delete_task",
                "arguments": {
                    "target_text": "Morning Exercise"
                },
            },
        },
    )

    preview_response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message": "Delete morning exercise task",
            "timezone": "+05:30",
        },
        headers={
            "X-Gemini-Api-Key": "test-key",
        },
    )

    assert preview_response.status_code == 200

    preview = preview_response.get_json()["data"]

    assert preview["status"] == "ready"

    assert (
        preview["command"]["action"]
        == "delete_recurring_task"
    )

    response = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id": preview["draft_id"],
            "confirmed": True,
        },
    )

    assert response.status_code == 200

    assert (
        db.tasks.find_one(
            {"_id": task_id}
        )
        is None
    )

    assert (
        db.task_occurrences.find_one(
            {"_id": occurrence_id}
        )
        is None
    )



def test_delete_preview_bypasses_gemini(
    client,
    monkeypatch,
):
    """
    A clear delete command must work even when Gemini is
    unavailable because delete intent parsing is deterministic.
    """

    from datetime import datetime, timezone

    db = get_db()

    task_id = db.tasks.insert_one(
        {
            "task_type":
                "repeat_until_done",

            "title":
                "Swim",

            "description":
                "Swimming task",

            "priority":
                "not_important_not_urgent",

            "duration": {
                "start_date":
                    "2026-09-24",

                "end_date":
                    "2026-10-24",
            },

            "repeat": {
                "type":
                    "everyday",

                "custom_dates":
                    [],
            },

            "reminders":
                [],

            "status":
                "pending",

            "reminders_cancelled":
                False,

            "created_at":
                datetime.now(
                    timezone.utc
                ),

            "updated_at":
                datetime.now(
                    timezone.utc
                ),
        }
    ).inserted_id

    def gemini_must_not_run(
        **kwargs,
    ):
        raise AssertionError(
            "Gemini must not be called "
            "for an explicit delete command."
        )

    monkeypatch.setattr(
        "src.modules.assistant.drafts."
        "service.parse_task_message",
        gemini_must_not_run,
    )

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message":
                "Delete swim task",

            "timezone":
                "+05:30",
        },
    )

    assert (
        response.status_code
        == 200
    )

    data = (
        response
        .get_json()["data"]
    )

    assert (
        data["status"]
        == "ready"
    )

    assert (
        data["command"]["action"]
        == "delete_repeat_until_done_task"
    )

    assert (
        data["command"]
        ["arguments"]
        ["task_id"]
        == str(task_id)
    )

    assert (
        data["command"]
        ["requires_confirmation"]
        is True
    )
