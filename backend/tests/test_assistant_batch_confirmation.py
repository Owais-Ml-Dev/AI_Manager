"""Step 1E: confirm/cancel Task 1 and advance exactly once."""

import pytest
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
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


def _batch(*titles):
    return create_task_batch(
        _parsed(*[_intent(title) for title in titles]),
        source_message=" and ".join(titles),
    )


def _make_review_ready(batch_id):
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    return continue_active_task(batch_id, "2")


def test_confirm_executes_task_one_then_activates_task_two():
    batch = _batch("Gym", "Call John")
    ready = _make_review_ready(batch["batch_id"])
    assert ready["draft"]["status"] == "ready"

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["resolved_task_number"] == 1
    assert result["batch_status"] == "in_progress"
    assert result["current_task_number"] == 2
    assert result["all_done"] is False

    db = get_db()
    assert db.tasks.count_documents({"title": "Gym"}) == 1

    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 1
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][1]["draft_id"] == (
        result["next_task"]["draft"]["draft_id"]
    )


def test_cancel_skips_task_one_without_execution_and_activates_task_two():
    batch = _batch("Gym", "Call John")
    ready = _make_review_ready(batch["batch_id"])
    draft_id = ready["draft"]["draft_id"]

    result = cancel_active_task(
        batch["batch_id"],
        draft_id,
    )

    assert result["resolution"] == "skipped"
    assert result["current_task_number"] == 2

    db = get_db()
    assert db.tasks.count_documents({}) == 0
    draft = db.assistant_drafts.find_one({"_id": ObjectId(draft_id)})
    assert draft["status"] == "cancelled"

    stored = db.assistant_task_batches.find_one({})
    assert stored["items"][0]["status"] == "skipped"
    assert stored["items"][1]["status"] == "active"


def test_confirm_not_ready_does_not_execute_or_advance():
    batch = _batch("Gym", "Call John")
    prepared = prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        confirm_active_task(
            batch["batch_id"],
            prepared["draft"]["draft_id"],
        )

    assert exc.value.status_code == 409

    db = get_db()
    assert db.tasks.count_documents({}) == 0
    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "pending"


def test_last_confirm_marks_batch_completed():
    batch = _batch("Gym")
    ready = _make_review_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["batch_status"] == "completed"
    assert result["current_index"] is None
    assert result["current_task_number"] is None
    assert result["active_item"] is None
    assert result["all_done"] is True

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["status"] == "completed"
    assert stored["current_index"] is None
    assert stored["items"][0]["status"] == "executed"


def test_last_cancel_marks_batch_completed_without_creating_task():
    batch = _batch("Gym")
    prepared = prepare_active_task(batch["batch_id"])

    result = cancel_active_task(
        batch["batch_id"],
        prepared["draft"]["draft_id"],
    )

    assert result["resolution"] == "skipped"
    assert result["batch_status"] == "completed"
    assert result["all_done"] is True
    assert get_db().tasks.count_documents({}) == 0


def test_confirmed_task_cannot_advance_batch_twice():
    batch = _batch("Gym", "Call John", "Pay Bill")
    ready = _make_review_ready(batch["batch_id"])
    old_draft_id = ready["draft"]["draft_id"]

    first = confirm_active_task(
        batch["batch_id"],
        old_draft_id,
    )
    assert first["current_task_number"] == 2

    # Even if Task 2 is prepared immediately, a late double-tap carrying the
    # old Task-1 draft id must never confirm Task 2.
    prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        confirm_active_task(
            batch["batch_id"],
            old_draft_id,
        )

    assert exc.value.status_code == 409

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["current_index"] == 1
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][2]["status"] == "pending"
    assert get_db().tasks.count_documents({"title": "Gym"}) == 1
