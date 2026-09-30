"""Task-control V2: skip-for-now, discard-current, discard-remaining."""

import pytest
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
    abort_task_batch,
    cancel_active_task,
    create_task_batch,
    defer_active_task,
    prepare_active_task,
)


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
        {
            "provider": "groq",
            "model": "test-model",
            "timezone": "UTC",
            "fallback_used": False,
            "attempted_providers": ["groq"],
            "intents": [_intent(title) for title in titles],
        },
        source_message=" and ".join(titles),
    )


def test_skip_for_now_preserves_draft_and_activates_next_task():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    result = defer_active_task(batch["batch_id"], first_draft_id)

    assert result["resolution"] == "deferred"
    assert result["resolved_task_number"] == 1
    assert result["current_task_number"] == 2
    assert result["next_task"]["current_task_number"] == 2

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["items"][0]["status"] == "deferred"
    assert stored["items"][0]["draft_id"] == first_draft_id
    assert stored["items"][1]["status"] == "active"


def test_deferred_task_is_revisited_after_pending_tasks_are_resolved():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    second = defer_active_task(batch["batch_id"], first_draft_id)["next_task"]
    third = cancel_active_task(
        batch["batch_id"],
        second["draft"]["draft_id"],
    )["next_task"]

    revisited = cancel_active_task(
        batch["batch_id"],
        third["draft"]["draft_id"],
    )["next_task"]

    assert revisited["current_task_number"] == 1
    assert revisited["draft"]["draft_id"] == first_draft_id

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "skipped"
    assert stored["items"][2]["status"] == "skipped"


def test_discard_remaining_also_discards_previously_deferred_tasks():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    second = defer_active_task(batch["batch_id"], first_draft_id)["next_task"]
    abort_task_batch(batch["batch_id"], second["draft"]["draft_id"])

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["status"] == "aborted"
    assert stored["current_index"] is None
    assert [item["status"] for item in stored["items"]] == [
        "discarded",
        "discarded",
        "discarded",
    ]

    first_draft = get_db().assistant_drafts.find_one(
        {"_id": ObjectId(first_draft_id)}
    )
    assert first_draft is not None
    assert first_draft["status"] == "cancelled"


def test_single_task_cannot_skip_for_now_without_destroying_state():
    batch = _batch("Only Task")
    active = prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as error:
        defer_active_task(batch["batch_id"], active["draft"]["draft_id"])

    assert error.value.status_code == 409
    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["status"] == "in_progress"
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
