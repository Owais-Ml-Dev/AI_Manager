"""Step 1C: active batch item -> existing assistant draft engine."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
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


def _intent(title="Gym", *, confirmed=False, complete=False, invalid=False):
    task = {"title": title}
    collect = {}

    if confirmed:
        collect.update(
            {
                "task_type_confirmed": True,
                "selected_task_action": "create_recurring_task",
            }
        )

    if complete or invalid:
        task.update(
            {
                "duration": {
                    "start_date": "2099-01-10" if invalid else "2099-01-01",
                    "end_date": "2099-01-01" if invalid else "2099-01-31",
                },
                "repeat": {
                    "type": "everyday",
                    "custom_dates": [],
                },
                "reminders": [
                    {
                        "start_time": "07:00",
                        "end_time": "08:00",
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

    arguments = {"task": task}
    if collect:
        arguments["collect"] = collect

    return {
        "action": "create_recurring_task",
        "arguments": arguments,
    }


def _batch_with_two(first):
    return create_task_batch(
        _parsed(
            first,
            _intent("Call John"),
        ),
        source_message="Create two tasks.",
    )


def test_prepare_task_one_asks_first_missing_field():
    batch = _batch_with_two(_intent())

    result = prepare_active_task(batch["batch_id"])

    assert result["current_task_number"] == 1
    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["task_type"]
    assert "Recurring or Repeat Until Done" in result["draft"]["question"]


def test_confirmed_task_type_skips_redundant_question():
    batch = _batch_with_two(_intent(confirmed=True))

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["duration"]


def test_present_but_invalid_information_is_not_review_ready():
    batch = _batch_with_two(
        _intent(confirmed=True, invalid=True)
    )

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["duration"]
    assert result["draft"]["validation_errors"]


def test_complete_valid_task_one_is_ready_for_review_only():
    batch = _batch_with_two(
        _intent(confirmed=True, complete=True)
    )

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] in {"ready", "duplicate_review"}
    assert result["draft"]["command"] is not None
    assert result["draft"]["command"]["requires_confirmation"] is True

    # Step 1C must not execute anything and must not activate Task 2.
    db = get_db()
    assert db.tasks.count_documents({}) == 0
    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][0]["draft_id"] == result["draft"]["draft_id"]
    assert stored["items"][1]["status"] == "pending"
    assert stored["items"][1]["draft_id"] is None


def test_prepare_active_task_is_idempotent():
    batch = _batch_with_two(_intent())

    first = prepare_active_task(batch["batch_id"])
    second = prepare_active_task(batch["batch_id"])

    assert first["draft"]["draft_id"] == second["draft"]["draft_id"]
    assert get_db().assistant_drafts.count_documents({}) == 1
