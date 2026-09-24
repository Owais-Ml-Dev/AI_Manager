"""Server-owned assistant draft workflow.

Flow:
    user text -> Gemini JSON parser -> draft -> deterministic validation
    -> duplicate/target matching -> user confirmation -> deterministic executor
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from src.modules.assistant.command_executor import (
    TaskCommandError,
    execute_task_command,
    validate_executable_command,
)
from src.modules.assistant.draft_validation import build_preview
from src.modules.assistant.duplicate_matcher import (
    find_create_duplicates,
    find_target_candidates,
    obvious_target,
)
from src.modules.assistant.drafts.repository import (
    claim_draft,
    find_draft,
    insert_draft,
    mark_executed,
    release_claim,
    update_draft,
)
from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderResponseError,
)
from src.modules.assistant.create_flow import (
    RETRY_QUESTIONS,
    apply_answer,
    local_intent,
    prefill_from_message,
    selected_create_action,
)
from src.modules.assistant.task_parser import (
    TaskParserError,
    local_now,
    parse_task_message,
)


DRAFT_TTL = timedelta(hours=1)

CREATE_ACTIONS = {"create_repeat_until_done_task", "create_recurring_task"}

# A reply this short that answered the pending question is handled without
# Gemini. Longer replies may carry other changes ("everyday, and rename it
# to Deep Study"), so those also go to Gemini -- but the plain-code reading
# of the asked field still wins.
SHORT_REPLY_WORDS = 8


class AssistantDraftError(Exception):
    def __init__(self, message, status_code=400, errors=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors


def _utc_now():
    return datetime.now(timezone.utc)


def _deep_merge(base, incoming):
    result = deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(incoming, dict):
        return result
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _task_of(intent):
    arguments = (intent or {}).get("arguments") or {}
    task = arguments.get("task")
    if not isinstance(task, dict):
        task = arguments.get("changes")
    return task if isinstance(task, dict) else {}


def _merge_intent(current, incoming, answering=False):
    """Combine the saved draft with what Gemini extracted from the new message.

    answering=True means the user is replying to a question we asked. A reply
    never changes WHAT is being done -- "everyday" answering "how often?" is
    not a new task and not an update to some other task -- so the draft's
    action is kept and only the fields are merged.
    """

    if not isinstance(current, dict) or not current:
        return deepcopy(incoming)
    if not isinstance(incoming, dict):
        return deepcopy(current)

    current_action = current.get("action")
    incoming_action = incoming.get("action")

    # A short follow-up such as "14 days" can classify as unknown.
    if incoming_action == "unknown" and current_action:
        incoming_action = current_action

    if answering and current_action in CREATE_ACTIONS:
        incoming_action = current_action

    # Recurring <-> repeat-until-done: both are "create a task". Switching
    # between them must KEEP what the user already told us. The old code
    # started a fresh intent here, silently dropping the title/repeat, which
    # made the assistant ask the same question again.
    if current_action in CREATE_ACTIONS and incoming_action in CREATE_ACTIONS:
        task = _deep_merge(_task_of(current), _task_of(incoming))
        collect = deepcopy((current.get("arguments") or {}).get("collect") or {})
        return {
            "action": incoming_action,
            "arguments": {"task": task, "collect": collect},
        }

    # A genuinely different request starts a fresh intent.
    if incoming_action and current_action and incoming_action != current_action:
        return {
            "action": incoming_action,
            "arguments": deepcopy(incoming.get("arguments") or {}),
        }

    return {
        "action": incoming_action or current_action,
        "arguments": _deep_merge(
            current.get("arguments") or {},
            incoming.get("arguments") or {},
        ),
    }


def _with_task(intent, task, collect=None):
    arguments = {**(intent.get("arguments") or {}), "task": task}
    if collect is not None:
        arguments["collect"] = collect
    return {"action": intent.get("action"), "arguments": arguments}


def _collect_of(intent):
    return dict(((intent or {}).get("arguments") or {}).get("collect") or {})


def _summary_for_target(action, candidate, changes=None):
    title = candidate.get("title") or "task"
    if action == "update_task":
        fields = ", ".join(sorted((changes or {}).keys()))
        suffix = f" ({fields})" if fields else ""
        return f"Update {title}{suffix}."
    if action == "complete_task":
        return f"Complete {title}."
    if action == "delete_task":
        return f"Delete {title}."
    return f"Use {title}."


def _materialize_target_command(intent, candidate):
    action = intent.get("action")
    arguments = intent.get("arguments") or {}
    task_type = candidate.get("task_type")

    if action == "update_task":
        changes = deepcopy(arguments.get("changes") or {})
        concrete = (
            "update_repeat_until_done_task"
            if task_type == "repeat_until_done"
            else "update_recurring_task"
        )
        command_arguments = {
            "task_id": candidate["id"],
            "changes": changes,
        }

    elif action == "complete_task":
        if task_type == "repeat_until_done":
            concrete = "complete_repeat_until_done_task"
            command_arguments = {"task_id": candidate["id"]}
        else:
            occurrence_id = candidate.get("occurrence_id")
            if not occurrence_id:
                raise AssistantDraftError(
                    "That recurring task has no pending occurrence today.", 409
                )
            concrete = "complete_recurring_occurrence"
            command_arguments = {"occurrence_id": occurrence_id}

    elif action == "delete_task":
        concrete = (
            "delete_repeat_until_done_task"
            if task_type == "repeat_until_done"
            else "delete_recurring_task"
        )
        command_arguments = {"task_id": candidate["id"]}

    else:
        raise AssistantDraftError("Unsupported target action.", 400)

    command = {
        "action": concrete,
        "arguments": command_arguments,
        "summary": _summary_for_target(
            action,
            candidate,
            arguments.get("changes"),
        ),
        "requires_confirmation": True,
    }

    try:
        validate_executable_command(command)
    except TaskCommandError as error:
        raise AssistantDraftError(
            error.message,
            error.status_code,
            error.errors,
        ) from error

    return command


def _response(document):
    return {
        "provider": document.get("provider", "gemini"),
        "type": "api",
        "model": document.get("model", ""),
        "timezone": document.get("timezone", "UTC"),
        "draft_id": str(document["_id"]),
        "status": document.get("status"),
        "question": document.get("question"),
        "missing_fields": document.get("missing_fields", []),
        "validation_errors": document.get("validation_errors", {}),
        "command": document.get("command"),
        "duplicate_matches": document.get("duplicate_matches", []),
        "target_matches": document.get("target_matches", []),
        "suggestions": document.get("suggestions", []),
    }


def _evaluate_intent(intent, today_date):
    preview = build_preview(intent)

    if preview["status"] == "resolve_target":
        target_text = (intent.get("arguments") or {}).get("target_text", "")
        candidates = find_target_candidates(
            target_text,
            intent.get("action"),
            today_date,
            limit=5,
        )

        if not candidates:
            preview.update(
                {
                    "status": "needs_input",
                    "question": (
                        f"I couldn't find an active task matching "
                        f"'{target_text}'. Which task do you mean?"
                    ),
                    "target_matches": [],
                }
            )
            return preview

        obvious = obvious_target(candidates)
        if obvious is not None:
            try:
                command = _materialize_target_command(intent, obvious)
            except AssistantDraftError as error:
                preview.update(
                    {
                        "status": "needs_input",
                        "question": error.message,
                        "validation_errors": error.errors or {},
                        "target_matches": candidates,
                    }
                )
                return preview

            preview.update(
                {
                    "status": "ready",
                    "command": command,
                    "question": None,
                    "target_matches": candidates,
                    "selected_target_id": obvious["id"],
                }
            )
            return preview

        preview.update(
            {
                "status": "needs_target_selection",
                "question": "Which of these tasks did you mean?",
                "target_matches": candidates,
            }
        )
        return preview

    if preview["status"] == "ready" and preview.get("command"):
        command = preview["command"]
        if command.get("action", "").startswith("create_"):
            duplicates = find_create_duplicates(command, limit=3)
            if duplicates:
                preview.update(
                    {
                        "status": "duplicate_review",
                        "duplicate_matches": duplicates,
                        "question": (
                            "I found a similar active task. Create a new task "
                            "or update the existing one?"
                        ),
                    }
                )

    return preview


def preview_task_draft(
    message,
    timezone_name="UTC",
    api_key=None,
    draft_id=None,
):
    """Parse one user message and persist/update the server-owned draft.

    Order of work, cheapest first:

      1. The user is answering our question ("everyday", "2", "9 am to
         11 am"): read it with plain code. No Gemini call.
      2. A new request: Gemini reads it (task type, title, description,
         anything else stated). If Gemini is overloaded, a plain-code
         reading is used instead so the user is never blocked.
      3. Pick the next question in the fixed order, or show the
         confirmation card when everything is known.
    """

    existing = None
    current_intent = None
    if draft_id:
        existing = find_draft(draft_id)
        if existing is None:
            raise AssistantDraftError("Assistant draft was not found or expired.", 404)
        if existing.get("status") in {"executing", "executed", "cancelled"}:
            raise AssistantDraftError(
                "This assistant draft is already finished. Start a new request.", 409
            )
        current_intent = existing.get("intent")

    today = local_now(timezone_name).date()

    current_action = (current_intent or {}).get("action")
    asked_field = (existing or {}).get("last_question_field")
    answering = (
        existing is not None
        and existing.get("status") == "needs_input"
        and current_action in CREATE_ACTIONS
        and bool(asked_field)
    )

    provider = (existing or {}).get("provider", "gemini")
    model = (existing or {}).get("model", "")

    intent = None
    local_answer = None

    # ---- 1. Answer to our question: plain code ------------------------
    if answering:
        task, collect, understood = apply_answer(
            asked_field,
            current_action,
            _task_of(current_intent),
            _collect_of(current_intent),
            message,
            today,
        )
        if understood:

            resolved_action = (
                selected_create_action(
                    current_action,
                    collect,
                )
            )

            local_answer = _with_task(
                {
                    **current_intent,
                    "action":
                        resolved_action,
                },
                task,
                collect,
            )

            if (
                len(
                    message.split()
                )
                <= SHORT_REPLY_WORDS
            ):
                intent = local_answer

    # ---- 2. Gemini --------------------------------------------------------
    if intent is None:
        try:
            parsed = parse_task_message(
                message=message,
                timezone_name=timezone_name,
                api_key=api_key,
                current_draft=current_intent,
                pending_question=(existing or {}).get("question") if answering else None,
            )
        except (ProviderConnectionError, ProviderResponseError) as error:
            if local_answer is not None:
                intent = local_answer
            elif not answering and (fallback := local_intent(message, today)):
                # Gemini is overloaded/unreachable, but this is a plain
                # "create X" request we can read ourselves.
                print(f"[assistant] Gemini unavailable ({error}); using local parse.", flush=True)
                intent = fallback
                model = "offline parser"
                if intent["action"] in CREATE_ACTIONS:
                    task, collect = (
                        prefill_from_message(
                            intent["action"],
                            _task_of(intent),
                            {},
                            message,
                            today,
                        )
                    )

                    resolved_action = (
                        selected_create_action(
                            intent["action"],
                            collect,
                        )
                    )

                    intent = _with_task(
                        {
                            **intent,
                            "action":
                                resolved_action,
                        },
                        task,
                        collect,
                    )
            else:
                raise
        else:
            provider = parsed["provider"]
            model = parsed["model"]
            intent = _merge_intent(current_intent, parsed["intent"], answering=answering)

            if intent.get("action") in CREATE_ACTIONS:
                action = intent["action"]
                task = _task_of(intent)
                collect = _collect_of(intent)

                if answering:
                    # The plain-code reading of the asked field wins.
                    task, collect, _ = apply_answer(
                        asked_field, action, task, collect, message, today
                    )
                else:
                    task, collect = prefill_from_message(
                        action, task, collect, message, today
                    )
                resolved_action = (
                    selected_create_action(
                        action,
                        collect,
                    )
                )

                intent = _with_task(
                    {
                        **intent,
                        "action":
                            resolved_action,
                    },
                    task,
                    collect,
                )

    evaluated = _evaluate_intent(
        intent,
        today.isoformat(),
    )

    # ---- 3. Never ask the exact same question twice in a row -----------
    question = evaluated.get("question")
    question_field = (evaluated.get("missing_fields") or [None])[0]
    ask_count = 1
    if (
        existing is not None
        and question_field
        and evaluated.get("status") == "needs_input"
        and existing.get("last_question_field") == question_field
        and existing.get("last_question_text") == question
        and not evaluated.get("validation_errors")
    ):
        # The answer did not move us forward: ask more precisely.
        ask_count = int(existing.get("ask_count") or 1) + 1
        question = RETRY_QUESTIONS.get(question_field, question)

    now = _utc_now()
    fields = {
        "status": evaluated.get("status", "collecting"),
        "intent": evaluated.get("intent", intent),
        "command": evaluated.get("command"),
        "question": question,
        "missing_fields": evaluated.get("missing_fields", []),
        "validation_errors": evaluated.get("validation_errors", {}),
        "duplicate_matches": evaluated.get("duplicate_matches", []),
        "target_matches": evaluated.get("target_matches", []),
        "selected_target_id": evaluated.get("selected_target_id"),
        "suggestions": (
            evaluated.get("suggestions", [])
            if evaluated.get("status") == "needs_input"
            else []
        ),
        "last_question_field": question_field if evaluated.get("status") == "needs_input" else None,
        # The plain question before any "Sorry, ..." rewording, so a
        # repeated question can be detected.
        "last_question_text": evaluated.get("question"),
        "ask_count": ask_count,
        "provider": provider,
        "model": model,
        "timezone": timezone_name,
        "updated_at": now,
        "expires_at": now + DRAFT_TTL,
    }

    if existing is None:
        document = {
            **fields,
            "created_at": now,
            "executed_at": None,
            "result": None,
        }
        inserted_id = insert_draft(document)
        document["_id"] = inserted_id
    else:
        document = update_draft(draft_id, fields)

    return _response(document)


def select_draft_target(draft_id, task_id):
    draft = find_draft(draft_id)
    if draft is None:
        raise AssistantDraftError("Assistant draft was not found or expired.", 404)
    if draft.get("status") != "needs_target_selection":
        raise AssistantDraftError("This draft does not need target selection.", 409)

    matches = draft.get("target_matches") or []
    candidate = next((item for item in matches if item.get("id") == task_id), None)
    if candidate is None:
        raise AssistantDraftError("Select one of the server-provided task matches.", 400)

    command = _materialize_target_command(draft.get("intent") or {}, candidate)
    now = _utc_now()
    updated = update_draft(
        draft_id,
        {
            "status": "ready",
            "command": command,
            "question": None,
            "selected_target_id": task_id,
            "updated_at": now,
            "expires_at": now + DRAFT_TTL,
        },
    )
    return _response(updated)


def _duplicate_update_command(draft, candidate_id):
    matches = draft.get("duplicate_matches") or []
    candidate = next((item for item in matches if item.get("id") == candidate_id), None)
    if candidate is None:
        raise AssistantDraftError(
            "Select one of the server-provided duplicate matches.", 400
        )

    original = draft.get("command") or {}
    task = deepcopy((original.get("arguments") or {}).get("task") or {})
    task_type = candidate.get("task_type")

    allowed = {
        "repeat_until_done": {
            "title",
            "description",
            "priority",
            "repeat",
            "reminders",
        },
        "recurring": {
            "title",
            "description",
            "priority",
            "duration",
            "repeat",
            "reminders",
        },
    }[task_type]

    changes = {key: value for key, value in task.items() if key in allowed}
    action = (
        "update_repeat_until_done_task"
        if task_type == "repeat_until_done"
        else "update_recurring_task"
    )

    command = {
        "action": action,
        "arguments": {"task_id": candidate_id, "changes": changes},
        "summary": f"Update existing {candidate.get('title') or 'task'}.",
        "requires_confirmation": True,
    }
    validate_executable_command(command)
    return command


def execute_task_draft(
    draft_id,
    confirmed=False,
    duplicate_decision=None,
    candidate_id=None,
):
    """Execute the server-owned command at most once."""

    draft = find_draft(draft_id)
    if draft is None:
        raise AssistantDraftError("Assistant draft was not found or expired.", 404)

    status = draft.get("status")
    if status == "executed":
        raise AssistantDraftError("This draft has already been executed.", 409)
    if status == "executing":
        raise AssistantDraftError("This draft is already being executed.", 409)
    if status not in {"ready", "duplicate_review"}:
        raise AssistantDraftError("This draft is not ready to execute.", 409)

    command = draft.get("command")
    if not isinstance(command, dict):
        raise AssistantDraftError("This draft has no executable command.", 409)

    if status == "duplicate_review":
        if duplicate_decision == "create_new":
            pass
        elif duplicate_decision == "update_existing":
            if not isinstance(candidate_id, str) or not candidate_id.strip():
                raise AssistantDraftError("candidate_id is required.", 400)
            try:
                command = _duplicate_update_command(draft, candidate_id)
            except TaskCommandError as error:
                raise AssistantDraftError(
                    error.message, error.status_code, error.errors
                ) from error
        else:
            raise AssistantDraftError(
                "Choose create_new or update_existing before confirming.", 409
            )

    normalized = validate_executable_command(command)
    if normalized.get("requires_confirmation") and confirmed is not True:
        raise AssistantDraftError(
            "This task command requires confirmation before execution.", 409
        )

    now = _utc_now()
    claimed = claim_draft(draft_id, {status}, now)
    if claimed is None:
        raise AssistantDraftError(
            "This draft was already claimed by another request.", 409
        )

    try:
        result = execute_task_command(command)
    except TaskCommandError as error:
        release_claim(draft_id, status, _utc_now(), error.message)
        raise AssistantDraftError(
            error.message, error.status_code, error.errors
        ) from error

    executed_at = _utc_now()
    mark_executed(draft_id, executed_at, result, command)
    return result
