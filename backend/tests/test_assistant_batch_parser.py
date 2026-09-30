from unittest.mock import patch

import pytest

pytestmark = pytest.mark.no_db

from src.modules.assistant.batch_parser import (
    TaskBatchParserError,
    parse_task_batch_message,
)


def _route(result):
    return {
        "provider": "groq",
        "type": "api",
        "model": "test-model",
        "result": result,
        "fallback_used": False,
        "attempted_providers": ["groq"],
    }


def test_batch_parser_preserves_task_order():
    provider_result = {
        "tasks": [
            {
                "action": "create_recurring_task",
                "task": {
                    "title": "Gym",
                    "description": "Go to the gym.",
                    "repeat_type": "everyday",
                },
            },
            {
                "action": "create_repeat_until_done_task",
                "task": {
                    "title": "Pay electricity",
                    "description": "Pay the electricity bill.",
                    "start_date": "2026-10-02",
                    "end_date": "2026-10-02",
                },
            },
            {
                "action": "create_recurring_task",
                "task": {
                    "title": "Call John",
                    "description": "Call John.",
                    "repeat_type": "custom_dates",
                    "custom_dates": ["2026-10-04"],
                },
            },
        ]
    }

    with patch(
        "src.modules.assistant.batch_parser.structured_json_with_fallback",
        return_value=_route(provider_result),
    ):
        result = parse_task_batch_message(
            "Create gym daily, pay electricity Friday, and call John Sunday.",
            timezone_name="Asia/Kolkata",
        )

    assert result["task_count"] == 3
    assert [
        item["arguments"]["task"]["title"]
        for item in result["intents"]
    ] == ["Gym", "Pay electricity", "Call John"]


def test_batch_parser_allows_one_task():
    provider_result = {
        "tasks": [
            {
                "action": "create_repeat_until_done_task",
                "task": {
                    "title": "Pay rent",
                    "description": "Pay rent.",
                },
            }
        ]
    }

    with patch(
        "src.modules.assistant.batch_parser.structured_json_with_fallback",
        return_value=_route(provider_result),
    ):
        result = parse_task_batch_message("Create a pay rent task.")

    assert result["task_count"] == 1


def test_batch_parser_rejects_non_create_action():
    provider_result = {
        "tasks": [
            {
                "action": "delete_task",
                "task": {"title": "Gym"},
            }
        ]
    }

    with patch(
        "src.modules.assistant.batch_parser.structured_json_with_fallback",
        return_value=_route(provider_result),
    ):
        with pytest.raises(TaskBatchParserError) as error:
            parse_task_batch_message("Delete gym.")

    assert error.value.status_code == 422


def test_batch_parser_rejects_empty_task_array():
    with patch(
        "src.modules.assistant.batch_parser.structured_json_with_fallback",
        return_value=_route({"tasks": []}),
    ):
        with pytest.raises(TaskBatchParserError) as error:
            parse_task_batch_message("Hello")

    assert error.value.status_code == 422
