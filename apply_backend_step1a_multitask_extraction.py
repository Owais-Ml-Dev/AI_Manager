from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python apply_backend_step1a_multitask_extraction.py <backend-folder>"
    )

backend = Path(sys.argv[1]).resolve()
if not (backend / "src/modules/assistant/task_parser.py").exists():
    raise SystemExit(f"Not a valid backend folder: {backend}")

files = {
    backend / "src/modules/assistant/prompts/task_batch_prompt.py": '''"""Prompt for extracting multiple independent task-create intents."""

TASK_BATCH_SYSTEM_PROMPT = """
You split one user message into an ordered list of independent tasks for a
Task Manager. Output only JSON allowed by the response schema.

Rules:
- Keep tasks in the exact order the user mentioned them.
- One real-world task = one array item.
- Do NOT split details such as dates, repeat rules, reminder windows, priority,
  or descriptions into separate tasks.
- Include only task CREATE requests. This parser is not for update, complete,
  delete, or list commands.
- If the message contains only one create task, return one item.
- Never invent information the user did not provide.
- For a create request that does not explicitly say Recurring or Repeat Until
  Done, choose the most likely create action only as a provisional parse. The
  backend will still ask the user to confirm the task type later.

For each task:
- action = create_recurring_task for a habit/routine on several dates within a
  date range.
- action = create_repeat_until_done_task for one thing to finish once while
  reminders continue until completion.
- title = short, clear, 2-5 words, capitalised.
- description = one short sentence using only the user's meaning.
- repeat_type = everyday | weekdays | weekends | custom_dates, only when said.
- custom_dates = YYYY-MM-DD values only when repeat_type is custom_dates.
- start_date / end_date = YYYY-MM-DD only when stated or directly resolvable
  from TODAY.
- reminders use 24-hour HH:MM and only when unambiguous.
- priority only when the user states it.
""".strip()
''',
    backend / "src/modules/assistant/batch_parser.py": '''"""Pure multi-task parser for assistant create requests.

This module performs language -> ordered structured intents only. It has no
MongoDB access and does not create, update, or execute task drafts.
"""

import json
import time

from src.modules.assistant.prompts.task_batch_prompt import TASK_BATCH_SYSTEM_PROMPT
from src.modules.assistant.providers.provider_router import structured_json_with_fallback
from src.modules.assistant.task_parser import (
    _sanitize_task_fields,
    _task_fields_schema,
    local_now,
)


BATCH_CREATE_ACTIONS = {
    "create_repeat_until_done_task",
    "create_recurring_task",
}

MAX_BATCH_TASKS = 10

TASK_BATCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_BATCH_TASKS,
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(BATCH_CREATE_ACTIONS),
                    },
                    "task": _task_fields_schema(),
                },
                "required": ["action", "task"],
            },
        }
    },
    "required": ["tasks"],
}


class TaskBatchParserError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _sanitize_batch(value):
    if not isinstance(value, dict):
        raise TaskBatchParserError(
            "AI provider did not return a JSON object for task extraction.",
            502,
        )

    raw_tasks = value.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise TaskBatchParserError(
            "No task-create requests were extracted from the message.",
            422,
        )

    if len(raw_tasks) > MAX_BATCH_TASKS:
        raise TaskBatchParserError(
            f"A maximum of {MAX_BATCH_TASKS} tasks can be created in one message.",
            400,
        )

    intents = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            raise TaskBatchParserError(
                f"Task {index + 1} has an invalid structure.",
                502,
            )

        action = item.get("action")
        if action not in BATCH_CREATE_ACTIONS:
            raise TaskBatchParserError(
                f"Task {index + 1} is not a supported create action.",
                422,
            )

        fields = _sanitize_task_fields(item.get("task"))
        intents.append(
            {
                "action": action,
                "arguments": {"task": fields},
            }
        )

    return intents


def parse_task_batch_message(
    message,
    timezone_name="UTC",
    api_key=None,
    credentials=None,
):
    """Extract one or more ordered create intents from one user message.

    Step 1 intentionally does NOT connect this parser to the existing draft
    workflow. That happens only after this extraction layer is verified.
    """

    if not isinstance(message, str) or not message.strip():
        raise TaskBatchParserError("message is required.", 400)

    now = local_now(timezone_name)

    user_prompt = (
        f"TODAY: {now.date().isoformat()} ({now.strftime('%A')}), "
        f"time {now.strftime('%H:%M')}, timezone {timezone_name}\\n"
        f"USER MESSAGE: {message.strip()}"
    )

    started = time.monotonic()
    routed = structured_json_with_fallback(
        message=user_prompt,
        system_prompt=TASK_BATCH_SYSTEM_PROMPT,
        response_schema=TASK_BATCH_RESPONSE_SCHEMA,
        credentials=credentials,
        api_key=api_key,
    )

    intents = _sanitize_batch(routed.get("result"))

    print(
        "[assistant] %s batch parse %.1fs -> %s"
        % (
            routed.get("provider", "unknown"),
            time.monotonic() - started,
            json.dumps(intents, ensure_ascii=False)[:800],
        ),
        flush=True,
    )

    return {
        "provider": routed.get("provider", ""),
        "type": routed.get("type", "api"),
        "model": routed.get("model", ""),
        "timezone": timezone_name,
        "local_now": now,
        "intents": intents,
        "task_count": len(intents),
        "fallback_used": bool(routed.get("fallback_used", False)),
        "attempted_providers": routed.get("attempted_providers", []),
    }
''',
    backend / "tests/test_assistant_batch_parser.py": '''from unittest.mock import patch

import pytest

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
''',
}

for path, content in files.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".before_step1a.bak")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
            print(f"Backup: {backup}")
    path.write_text(content, encoding="utf-8")
    print(f"Updated: {path}")

print("\nSTEP 1A APPLIED")
print("No existing assistant flow was modified.")
print("Next run:")
print("  python -m py_compile src/modules/assistant/batch_parser.py src/modules/assistant/prompts/task_batch_prompt.py")
print("  pytest -q tests/test_assistant_batch_parser.py")
