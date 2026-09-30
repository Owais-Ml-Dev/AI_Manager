"""Step 1B tests: persistence and Task-1 activation only."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
    create_task_batch,
)


def _parsed_three_tasks():
    return {
        "provider": "groq",
        "model": "test-model",
        "timezone": "Asia/Kolkata",
        "fallback_used": False,
        "attempted_providers": ["groq"],
        "intents": [
            {
                "action": "create_recurring_task",
                "arguments": {"task": {"title": "Gym"}},
            },
            {
                "action": "create_repeat_until_done_task",
                "arguments": {"task": {"title": "Pay electricity"}},
            },
            {
                "action": "create_recurring_task",
                "arguments": {"task": {"title": "Call John"}},
            },
        ],
    }


def test_create_batch_persists_all_tasks_in_original_order():
    result = create_task_batch(
        _parsed_three_tasks(),
        source_message="Gym, pay electricity, call John.",
    )

    assert result["total_tasks"] == 3
    assert [
        item["intent"]["arguments"]["task"]["title"]
        for item in result["items"]
    ] == ["Gym", "Pay electricity", "Call John"]

    stored = get_db().assistant_task_batches.find_one({})
    assert stored is not None
    assert stored["total_tasks"] == 3
    assert stored["source_message"] == "Gym, pay electricity, call John."


def test_only_task_one_is_active():
    result = create_task_batch(_parsed_three_tasks())

    assert result["current_index"] == 0
    assert result["current_task_number"] == 1
    assert result["active_item"]["task_number"] == 1
    assert result["active_item"]["status"] == "active"
    assert [item["status"] for item in result["items"]] == [
        "active",
        "pending",
        "pending",
    ]


def test_step1b_does_not_create_assistant_drafts():
    create_task_batch(_parsed_three_tasks())

    db = get_db()
    assert db.assistant_task_batches.count_documents({}) == 1
    assert db.assistant_drafts.count_documents({}) == 0


def test_batch_rejects_empty_intents():
    with pytest.raises(AssistantBatchError) as error:
        create_task_batch({"intents": []})

    assert error.value.status_code == 400
