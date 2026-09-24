"""Deterministic assistant-draft validation and question generation."""

from copy import deepcopy

from src.modules.tasks.repeat_until_done.validation import (
    validate_create_repeat_until_done_task,
)
from src.modules.tasks.recurring.validation import validate_create_recurring_task

from src.modules.assistant.create_flow import (
    build_summary,
    default_description,
    next_step,
)


DEFAULT_PRIORITY = "not_important_not_urgent"


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _normalize_task(task):
    value = deepcopy(task) if isinstance(task, dict) else {}

    if _nonempty_string(value.get("title")):
        value["title"] = value["title"].strip()

    if "description" not in value:
        value["description"] = ""
    if "priority" not in value:
        # Deterministic application default; Gemini does not guess priority.
        value["priority"] = DEFAULT_PRIORITY

    repeat = value.get("repeat")
    if isinstance(repeat, dict) and repeat.get("type"):
        repeat = deepcopy(repeat)
        repeat.setdefault("custom_dates", [])
        value["repeat"] = repeat

    return value


def _create_missing_fields(action, task, collect=None):
    """Every field still needed, in the order the assistant asks for them."""

    missing = []
    step = next_step(action, task, collect or {})
    if step:
        missing.append(step["field"])
    return missing


def question_for_missing(field):
    questions = {
        "title": "What should I call this task?",
        "target_text": "Which task do you mean?",
        "changes": "What would you like to change about that task?",
    }
    return questions.get(field, "Please provide the missing task information.")


# A failed check clears the field it is about, so the normal step order asks
# for it again (with the reason in front of the question).
_ERROR_FIELD_RESET = (
    ("title", ("title",)),
    ("duration", ("duration",)),
    ("repeat", ("repeat",)),
    ("reminders", ("reminders",)),
)


def _first_error_message(errors):
    for value in errors.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Some details were not valid."


def build_create_preview(intent):
    """Validate a create intent without writing anything."""

    action = intent.get("action")
    arguments = intent.get("arguments") if isinstance(intent.get("arguments"), dict) else {}
    task = _normalize_task(arguments.get("task"))
    collect = dict(arguments.get("collect") or {})

    def needs(step, prefix=""):
        return {
            "status": "needs_input",
            "missing_fields": [step["field"]],
            "question": (prefix + " " + step["question"]).strip(),
            "suggestions": step.get("suggestions", []),
            "intent": {
                "action": action,
                "arguments": {"task": task, "collect": collect},
            },
            "command": None,
        }

    step = next_step(action, task, collect)
    if step:
        return needs(step)

    if not str(task.get("description") or "").strip():
        task["description"] = default_description(task.get("title", ""))

    if action == "create_repeat_until_done_task":
        errors = validate_create_repeat_until_done_task(task)
    else:
        errors = validate_create_recurring_task(task)

    if errors:
        reason = _first_error_message(errors)
        keys = " ".join(errors.keys())
        for prefix, fields in _ERROR_FIELD_RESET:
            if prefix in keys:
                for field in fields:
                    task.pop(field, None)
                if prefix == "reminders":
                    collect.pop(
                        "window_count",
                        None
                    )

                    collect.pop(
                        "confirmed_window_counts",
                        None
                    )

                break
        step = next_step(action, task, collect)
        if step:
            preview = needs(step, reason)
            preview["validation_errors"] = errors
            return preview
        return {
            "status": "needs_input",
            "missing_fields": [],
            "validation_errors": errors,
            "question": reason,
            "suggestions": [],
            "intent": {"action": action, "arguments": {"task": task, "collect": collect}},
            "command": None,
        }

    command = {
        "action": action,
        "arguments": {"task": task},
        "summary": build_summary(action, task),
        "requires_confirmation": True,
    }

    return {
        "status": "ready",
        "missing_fields": [],
        "question": None,
        "suggestions": [],
        "intent": {
            "action": action,
            "arguments": {"task": task, "collect": collect},
        },
        "command": command,
    }


def build_generic_preview(intent):
    """Validate non-create language before database target resolution."""

    action = intent.get("action")
    arguments = intent.get("arguments") if isinstance(intent.get("arguments"), dict) else {}

    if action == "list_active_tasks":
        return {
            "status": "ready",
            "missing_fields": [],
            "question": None,
            "intent": {"action": action, "arguments": {}},
            "command": {
                "action": "list_active_tasks",
                "arguments": {},
                "summary": "List active tasks.",
                "requires_confirmation": False,
            },
        }

    if action == "unknown":
        return {
            "status": "needs_input",
            "missing_fields": [],
            "question": "What task would you like me to create or change?",
            "intent": intent,
            "command": None,
        }

    target = arguments.get("target_text")
    if not _nonempty_string(target):
        return {
            "status": "needs_input",
            "missing_fields": ["target_text"],
            "question": question_for_missing("target_text"),
            "intent": intent,
            "command": None,
        }

    if action == "update_task":
        changes = _normalize_task(arguments.get("changes"))
        # Defaults are inappropriate for updates. Keep only fields the model
        # actually extracted.
        original_changes = arguments.get("changes")
        changes = deepcopy(original_changes) if isinstance(original_changes, dict) else {}
        if not changes:
            return {
                "status": "needs_input",
                "missing_fields": ["changes"],
                "question": question_for_missing("changes"),
                "intent": intent,
                "command": None,
            }

    return {
        "status": "resolve_target",
        "missing_fields": [],
        "question": None,
        "intent": intent,
        "command": None,
    }


def build_preview(intent):
    action = intent.get("action") if isinstance(intent, dict) else None
    if action in {"create_repeat_until_done_task", "create_recurring_task"}:
        return build_create_preview(intent)
    return build_generic_preview(intent if isinstance(intent, dict) else {})
