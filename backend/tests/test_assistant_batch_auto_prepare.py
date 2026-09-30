"""Step 1F: resolve Task 1, then immediately prepare the next task."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    cancel_active_task,
    confirm_active_task,
    continue_active_task,
    create_task_batch,
    prepare_active_task,
)


def _parsed(*intents):
    return {
        "provider": "groq",
        "model": "test-model",
        "timezone": "UTC",
        "fallback_used": False,
        "attempted_providers": ["groq"],
        "intents": list(intents),
    }


def _intent(title, *, complete=False):
    task = {"title": title}
    collect = {
        "task_type_confirmed": True,
        "selected_task_action": "create_recurring_task",
    }

    if complete:
        task.update(
            {
                "duration": {
                    "start_date": "2099-02-01",
                    "end_date": "2099-02-28",
                },
                "repeat": {
                    "type": "everyday",
                    "custom_dates": [],
                },
                "reminders": [
                    {
                        "start_time": "09:00",
                        "end_time": "10:00",
                        "count": 2,
                    }
                ],
            }
        )
        collect.update(
            {
                "window_count": 1,
                "confirmed_window_counts": 1,
            }
        )

    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": task,
            "collect": collect,
        },
    }


def _batch(second_complete=False):
    return create_task_batch(
        _parsed(
            _intent("Gym"),
            _intent("Call John", complete=second_complete),
        ),
        source_message="Create Gym and Call John.",
    )


def _make_first_ready(batch_id):
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    return continue_active_task(batch_id, "2")


def test_confirm_immediately_prepares_task_two_and_returns_its_question():
    batch = _batch()
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["current_task_number"] == 2
    assert result["next_task_error"] is None

    next_task = result["next_task"]
    assert next_task is not None
    assert next_task["current_task_number"] == 2
    assert next_task["draft"]["status"] == "needs_input"
    assert next_task["draft"]["missing_fields"] == ["duration"]

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][1]["draft_id"] == next_task["draft"]["draft_id"]


def test_cancel_immediately_prepares_task_two_without_creating_task_one():
    batch = _batch()
    prepared = prepare_active_task(batch["batch_id"])

    result = cancel_active_task(
        batch["batch_id"],
        prepared["draft"]["draft_id"],
    )

    assert result["resolution"] == "skipped"
    assert result["current_task_number"] == 2
    assert result["next_task"] is not None
    assert result["next_task"]["draft"]["missing_fields"] == ["duration"]
    assert get_db().tasks.count_documents({}) == 0


def test_fully_specified_task_two_is_immediately_ready_for_review():
    batch = _batch(second_complete=True)
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    next_task = result["next_task"]
    assert next_task is not None
    assert next_task["current_task_number"] == 2
    assert next_task["draft"]["status"] in {"ready", "duplicate_review"}
    assert next_task["draft"]["command"] is not None
    assert next_task["draft"]["command"]["requires_confirmation"] is True

    # Task 2 has only reached review. It has not been executed.
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0


def test_last_task_resolution_has_no_next_task():
    batch = create_task_batch(
        _parsed(_intent("Gym")),
        source_message="Create Gym.",
    )
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["all_done"] is True
    assert result["batch_status"] == "completed"
    assert result["next_task"] is None
    assert result["next_task_error"] is None


def test_explicit_prepare_after_auto_prepare_reuses_same_task_two_draft():
    batch = _batch()
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )
    auto_draft_id = result["next_task"]["draft"]["draft_id"]

    repeated = prepare_active_task(batch["batch_id"])

    assert repeated["draft"]["draft_id"] == auto_draft_id
    assert get_db().assistant_drafts.count_documents({}) == 2
