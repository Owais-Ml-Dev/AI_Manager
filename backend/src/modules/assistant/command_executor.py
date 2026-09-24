"""Deterministic execution for already-parsed assistant task commands.

Gemini is intentionally absent from this module.  Every write goes through the
same task validation/services used by the normal REST API.
"""

from src.modules.tasks.repeat_until_done.service import (
    complete_repeat_until_done_task,
    create_repeat_until_done_task,
    delete_repeat_until_done_task,
    get_all_repeat_until_done_tasks,
    get_repeat_until_done_task,
    update_repeat_until_done_task,
)
from src.modules.tasks.repeat_until_done.validation import (
    validate_create_repeat_until_done_task,
    validate_update_repeat_until_done_task,
)
from src.modules.tasks.recurring.service import (
    complete_recurring_occurrence,
    create_recurring_task,
    delete_recurring_task,
    get_all_recurring_tasks,
    get_recurring_task,
    update_recurring_task,
)
from src.modules.tasks.recurring.validation import (
    validate_create_recurring_task,
    validate_update_recurring_task,
)


ALLOWED_EXECUTABLE_ACTIONS = {
    "list_active_tasks",
    "create_repeat_until_done_task",
    "create_recurring_task",
    "update_repeat_until_done_task",
    "update_recurring_task",
    "complete_repeat_until_done_task",
    "complete_recurring_occurrence",
    "delete_repeat_until_done_task",
    "delete_recurring_task",
}

MUTATING_ACTIONS = ALLOWED_EXECUTABLE_ACTIONS - {"list_active_tasks"}


class TaskCommandError(Exception):
    """Deterministic assistant-command failure."""

    def __init__(self, message, status_code=400, errors=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors


def normalize_executable_command(command):
    if not isinstance(command, dict):
        raise TaskCommandError("command must be an object.", 400)

    action = command.get("action")
    if action not in ALLOWED_EXECUTABLE_ACTIONS:
        raise TaskCommandError("Unsupported task command.", 400)

    arguments = command.get("arguments", {})
    if not isinstance(arguments, dict):
        raise TaskCommandError("command arguments must be an object.", 400)

    summary = command.get("summary")
    if not isinstance(summary, str):
        summary = ""

    return {
        "action": action,
        "arguments": arguments,
        "summary": summary.strip(),
        "requires_confirmation": action in MUTATING_ACTIONS,
    }


def validate_executable_command(command):
    """Re-use the normal task API validators before any service call."""

    normalized = normalize_executable_command(command)
    action = normalized["action"]
    arguments = normalized["arguments"]

    if action == "create_repeat_until_done_task":
        task = arguments.get("task")
        if not isinstance(task, dict):
            raise TaskCommandError(
                "Repeat Until Done task data is missing.", 422
            )
        errors = validate_create_repeat_until_done_task(task)
        if errors:
            raise TaskCommandError(
                "Repeat Until Done task failed validation.", 422, errors
            )

    elif action == "create_recurring_task":
        task = arguments.get("task")
        if not isinstance(task, dict):
            raise TaskCommandError("Recurring task data is missing.", 422)
        errors = validate_create_recurring_task(task)
        if errors:
            raise TaskCommandError(
                "Recurring task failed validation.", 422, errors
            )

    elif action == "update_repeat_until_done_task":
        task_id = arguments.get("task_id")
        changes = arguments.get("changes")
        if not isinstance(task_id, str) or not isinstance(changes, dict):
            raise TaskCommandError(
                "Repeat Until Done update is incomplete.", 422
            )
        current = get_repeat_until_done_task(task_id)
        if current is None:
            raise TaskCommandError(
                "The selected Repeat Until Done task no longer exists.", 404
            )
        errors = validate_update_repeat_until_done_task(changes)
        if errors:
            raise TaskCommandError(
                "Repeat Until Done update failed validation.", 422, errors
            )

    elif action == "update_recurring_task":
        task_id = arguments.get("task_id")
        changes = arguments.get("changes")
        if not isinstance(task_id, str) or not isinstance(changes, dict):
            raise TaskCommandError("Recurring update is incomplete.", 422)
        current = get_recurring_task(task_id)
        if current is None:
            raise TaskCommandError(
                "The selected recurring task no longer exists.", 404
            )
        errors = validate_update_recurring_task(changes, current)
        if errors:
            raise TaskCommandError(
                "Recurring update failed validation.", 422, errors
            )

    elif action in {
        "complete_repeat_until_done_task",
        "delete_repeat_until_done_task",
        "delete_recurring_task",
    }:
        task_id = arguments.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise TaskCommandError("task_id is required.", 422)

    elif action == "complete_recurring_occurrence":
        occurrence_id = arguments.get("occurrence_id")
        if not isinstance(occurrence_id, str) or not occurrence_id.strip():
            raise TaskCommandError("occurrence_id is required.", 422)

    return normalized


def execute_task_command(command):
    """Execute one validated command. Gemini is never called here."""

    normalized = validate_executable_command(command)
    action = normalized["action"]
    arguments = normalized["arguments"]

    if action == "list_active_tasks":
        return {
            "action": action,
            "result": {
                "repeat_until_done": get_all_repeat_until_done_tasks(),
                "recurring": get_all_recurring_tasks(),
            },
        }

    if action == "create_repeat_until_done_task":
        result = create_repeat_until_done_task(arguments["task"])

    elif action == "create_recurring_task":
        result = create_recurring_task(arguments["task"])

    elif action == "update_repeat_until_done_task":
        result = update_repeat_until_done_task(
            arguments["task_id"], arguments["changes"]
        )
        if result == "not_found":
            raise TaskCommandError("Repeat Until Done task not found.", 404)
        if result == "completed":
            raise TaskCommandError(
                "Completed Repeat Until Done tasks cannot be updated.", 409
            )

    elif action == "update_recurring_task":
        result = update_recurring_task(
            arguments["task_id"], arguments["changes"]
        )
        if result == "not_found":
            raise TaskCommandError("Recurring task not found.", 404)
        if result == "inactive":
            raise TaskCommandError(
                "Inactive recurring tasks cannot be updated.", 409
            )

    elif action == "complete_repeat_until_done_task":
        result = complete_repeat_until_done_task(arguments["task_id"])
        if result == "not_found":
            raise TaskCommandError("Repeat Until Done task not found.", 404)
        if result == "already_completed":
            raise TaskCommandError(
                "Repeat Until Done task is already completed.", 409
            )

    elif action == "complete_recurring_occurrence":
        result = complete_recurring_occurrence(arguments["occurrence_id"])
        if result == "not_found":
            raise TaskCommandError("Recurring occurrence not found.", 404)
        if result == "already_completed":
            raise TaskCommandError(
                "Recurring occurrence is already completed.", 409
            )
        if result == "missed":
            raise TaskCommandError(
                "A missed recurring occurrence cannot be completed.", 409
            )
        if result == "already_processed":
            raise TaskCommandError(
                "Recurring occurrence has already been processed.", 409
            )

    elif action == "delete_repeat_until_done_task":
        deleted = delete_repeat_until_done_task(arguments["task_id"])
        if not deleted:
            raise TaskCommandError("Repeat Until Done task not found.", 404)
        result = {"deleted": True, "task_id": arguments["task_id"]}

    elif action == "delete_recurring_task":
        deleted = delete_recurring_task(arguments["task_id"])
        if not deleted:
            raise TaskCommandError("Recurring task not found.", 404)
        result = {"deleted": True, "task_id": arguments["task_id"]}

    else:  # defensive; the normalizer already whitelists actions
        raise TaskCommandError("Unsupported task command.", 400)

    return {"action": action, "result": result}
