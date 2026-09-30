"""Step 1D: continue Task 1 until it becomes review-ready."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
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


def _intent(title, confirmed=True):
    collect = {}
    if confirmed:
        collect = {
            "task_type_confirmed": True,
            "selected_task_action": "create_recurring_task",
        }

    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": {"title": title},
            "collect": collect,
        },
    }


def _batch():
    return create_task_batch(
        _parsed(
            _intent("Gym"),
            _intent("Call John"),
        ),
        source_message="Create Gym and Call John.",
    )


def test_followup_moves_task_one_to_next_missing_field():
    batch = _batch()
    first = prepare_active_task(batch["batch_id"])
    assert first["draft"]["missing_fields"] == ["duration"]

    result = continue_active_task(
        batch["batch_id"],
        "1 Jan 2099 to 31 Jan 2099",
    )

    assert result["current_task_number"] == 1
    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["repeat"]


def test_followups_can_reach_review_without_advancing_task_two():
    batch = _batch()
    batch_id = batch["batch_id"]
    prepare_active_task(batch_id)

    result = continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    assert result["draft"]["missing_fields"] == ["repeat"]

    result = continue_active_task(batch_id, "Every day")
    assert result["draft"]["missing_fields"] == ["reminders.count"]

    result = continue_active_task(batch_id, "1")
    assert result["draft"]["missing_fields"] == ["reminders.window"]

    result = continue_active_task(batch_id, "7 am to 8 am")
    assert result["draft"]["missing_fields"] == [
        "reminders.window_reminder_count"
    ]

    result = continue_active_task(batch_id, "2")
    assert result["draft"]["status"] in {"ready", "duplicate_review"}
    assert result["draft"]["command"] is not None
    assert result["draft"]["command"]["requires_confirmation"] is True

    db = get_db()
    assert db.tasks.count_documents({}) == 0

    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "pending"
    assert stored["items"][1]["draft_id"] is None


def test_review_ready_task_ignores_extra_followup_and_stays_same_draft():
    batch = _batch()
    batch_id = batch["batch_id"]
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    ready = continue_active_task(batch_id, "2")

    repeated = continue_active_task(batch_id, "change the title")

    assert repeated["draft"]["draft_id"] == ready["draft"]["draft_id"]
    assert repeated["draft"]["status"] == ready["draft"]["status"]
    assert repeated["draft"]["command"] == ready["draft"]["command"]
    assert get_db().tasks.count_documents({}) == 0


def test_blank_followup_is_rejected_without_changing_batch():
    batch = _batch()
    prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        continue_active_task(batch["batch_id"], "   ")

    assert exc.value.status_code == 400
    stored = get_db().assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][1]["status"] == "pending"
