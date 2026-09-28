"""Pure Gemini task parser: natural language -> structured JSON only.

This module intentionally imports no task services, repositories, or database
code.  It cannot read or mutate user tasks.
"""

import json
import re
import time
from datetime import datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.modules.assistant.prompts.task_command_prompt import TASK_COMMAND_SYSTEM_PROMPT
from src.modules.assistant.providers.provider_factory import create_provider


PARSER_ACTIONS = [
    "create_repeat_until_done_task",
    "create_recurring_task",
    "update_task",
    "complete_task",
    "delete_task",
    "list_active_tasks",
    "unknown",
]

_PRIORITY_VALUES = [
    "important_urgent",
    "important_not_urgent",
    "not_important_urgent",
    "not_important_not_urgent",
]

_REPEAT_VALUES = [
    "everyday",
    "weekdays",
    "weekends",
    "custom_dates",
]


def _task_fields_schema():
    """Flat field list for Gemini.

    Gemini's structured output is most reliable with a flat object of simple
    fields. The previous nested shape ({"repeat": {"type": ...}},
    {"duration": {"start_date": ...}}) was optional at every level, and the
    model frequently returned the parent object empty or skipped it -- which
    is how "every day" in the user's message never reached the draft.

    The backend converts these flat fields back into the nested shape the
    task services expect (see _sanitize_task_fields).
    """

    reminder_schema = {
        "type": "object",
        "properties": {
            "start_time": {"type": "string", "description": "HH:MM, 24-hour"},
            "end_time": {"type": "string", "description": "HH:MM, 24-hour"},
            "count": {"type": "integer"},
        },
        "required": ["start_time", "end_time", "count"],
    }

    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": _PRIORITY_VALUES},
            "repeat_type": {"type": "string", "enum": _REPEAT_VALUES},
            "custom_dates": {
                "type": "array",
                "items": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "reminders": {
                "type": "array",
                "items": reminder_schema,
            },
        },
    }


TASK_INTENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": PARSER_ACTIONS,
        },
        "task": _task_fields_schema(),
        "target_text": {"type": "string"},
    },
    "required": ["action"],
}


class TaskParserError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def local_now(timezone_name):
    """Resolve UTC offsets and IANA timezone names supplied by Flutter."""

    value = str(timezone_name or "UTC").strip() or "UTC"

    if value.upper() in {"UTC", "GMT", "Z"}:
        return datetime.now(datetime_timezone.utc)

    match = re.fullmatch(
        r"(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3) or "0")
        if hours > 23 or minutes > 59:
            raise TaskParserError("Invalid timezone.", 400)
        offset = datetime_timezone(
            timedelta(minutes=sign * (hours * 60 + minutes))
        )
        return datetime.now(offset)

    try:
        resolved = ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise TaskParserError("Invalid timezone.", 400) from error

    return datetime.now(resolved)


def _sanitize_task_fields(value):
    """Convert Gemini's flat fields into the nested task shape.

    Accepts the old nested shape too, so a draft saved before this change
    still works.
    """

    if not isinstance(value, dict):
        return {}

    task = {}

    for key in ("title", "description", "priority"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            task[key] = item.strip()

    # Repeat -------------------------------------------------------
    repeat_type = value.get("repeat_type")
    custom_dates = value.get("custom_dates")
    nested_repeat = value.get("repeat")
    if isinstance(nested_repeat, dict) and not repeat_type:
        repeat_type = nested_repeat.get("type")
        custom_dates = nested_repeat.get("custom_dates", custom_dates)

    if repeat_type in _REPEAT_VALUES:
        dates = (
            [d for d in custom_dates if isinstance(d, str) and d.strip()]
            if isinstance(custom_dates, list)
            else []
        )
        task["repeat"] = {
            "type": repeat_type,
            "custom_dates": dates if repeat_type == "custom_dates" else [],
        }

    # Duration -----------------------------------------------------
    start_date = value.get("start_date")
    end_date = value.get("end_date")
    nested_duration = value.get("duration")
    if isinstance(nested_duration, dict):
        start_date = start_date or nested_duration.get("start_date")
        end_date = end_date or nested_duration.get("end_date")

    duration = {}
    if isinstance(start_date, str) and start_date.strip():
        duration["start_date"] = start_date.strip()
    if isinstance(end_date, str) and end_date.strip():
        duration["end_date"] = end_date.strip()
    if duration:
        task["duration"] = duration

    # Reminders ----------------------------------------------------
    reminders = value.get("reminders")
    if isinstance(reminders, list):
        clean = [item for item in reminders if isinstance(item, dict)]
        if clean:
            task["reminders"] = clean

    return task


def _sanitize_intent(value):
    if not isinstance(value, dict):
        raise TaskParserError("Gemini did not return a JSON object.", 502)

    action = value.get("action")
    if action not in PARSER_ACTIONS:
        raise TaskParserError("Gemini returned an unsupported task action.", 502)

    # New flat shape: {"action", "task", "target_text"}.
    # Old nested shape: {"action", "arguments": {"task"|"changes", ...}}.
    raw_arguments = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
    raw_task = value.get("task")
    if not isinstance(raw_task, dict):
        raw_task = raw_arguments.get("task") or raw_arguments.get("changes") or {}

    fields = _sanitize_task_fields(raw_task)

    arguments = {}
    if action == "update_task":
        arguments["changes"] = fields
    elif action in ("create_repeat_until_done_task", "create_recurring_task", "unknown"):
        arguments["task"] = fields

    target_text = value.get("target_text") or raw_arguments.get("target_text")
    if isinstance(target_text, str) and target_text.strip():
        arguments["target_text"] = target_text.strip()

    return {"action": action, "arguments": arguments}


def _flat_draft_for_prompt(current_draft):
    """Show Gemini the draft in the same flat shape it is asked to return."""

    if not isinstance(current_draft, dict) or not current_draft:
        return {}

    arguments = current_draft.get("arguments") or {}
    task = arguments.get("task") or arguments.get("changes") or {}
    flat = {"action": current_draft.get("action")}

    for key in ("title", "description", "priority", "reminders"):
        if task.get(key) not in (None, "", []):
            flat[key] = task[key]

    repeat = task.get("repeat") or {}
    if repeat.get("type"):
        flat["repeat_type"] = repeat["type"]
        if repeat.get("custom_dates"):
            flat["custom_dates"] = repeat["custom_dates"]

    duration = task.get("duration") or {}
    for key in ("start_date", "end_date"):
        if duration.get(key):
            flat[key] = duration[key]

    if arguments.get("target_text"):
        flat["target_text"] = arguments["target_text"]

    return flat


def parse_task_message(
    message,
    timezone_name="UTC",
    api_key=None,
    current_draft=None,
    pending_question=None,
):
    """Return a structured intent.  No task database is read here.

    pending_question: the question the assistant last asked, if the user is
    answering one. Without it a reply like "everyday" has no context.
    """

    if not isinstance(message, str) or not message.strip():
        raise TaskParserError("message is required.", 400)

    now = local_now(timezone_name)

    draft_json = json.dumps(
        _flat_draft_for_prompt(current_draft),
        ensure_ascii=False,
    )

    user_prompt = (
        f"TODAY: {now.date().isoformat()} ({now.strftime('%A')}), "
        f"time {now.strftime('%H:%M')}, timezone {timezone_name}\n"
        f"CURRENT DRAFT: {draft_json}\n"
        + (
            f"QUESTION THE USER IS ANSWERING: {pending_question}\n"
            if pending_question
            else ""
        )
        + f"USER MESSAGE: {message.strip()}"
    )

    provider = create_provider(api_key=api_key)
    started = time.monotonic()
    parsed = provider.structured_json(
        message=user_prompt,
        system_prompt=TASK_COMMAND_SYSTEM_PROMPT,
        response_schema=TASK_INTENT_RESPONSE_SCHEMA,
    )

    # Visible in the Flask terminal: what Gemini actually returned and how
    # long it took. If the assistant ever misunderstands something, this
    # line shows whether Gemini or the backend is responsible.
    print(
        "[assistant] Gemini parse %.1fs -> %s"
        % (time.monotonic() - started, json.dumps(parsed, ensure_ascii=False)[:500]),
        flush=True,
    )

    return {
        "provider": "gemini",
        "type": "api",
        "model": getattr(provider, "model_used", provider.model),
        "timezone": timezone_name,
        "local_now": now,
        "intent": _sanitize_intent(parsed),
    }
