"""Persistence boundary for ordered assistant task batches.

Step 1B intentionally does only this:
    parsed intents -> one batch document -> Task 1 active, remaining tasks pending

It does NOT create assistant drafts, ask follow-up questions, execute tasks, or
advance to Task 2. Those behaviors are added in later checkpoints.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from src.modules.assistant.batch_parser import (
    BATCH_CREATE_ACTIONS,
    MAX_BATCH_TASKS,
)
from bson.errors import InvalidId

from src.modules.assistant.batches.repository import (
    abort_active_batch,
    attach_draft_to_active_item,
    defer_active_item_and_activate,
    find_batch,
    insert_batch,
    resolve_active_item_and_advance,
)
from src.modules.assistant.drafts.service import (
    AssistantDraftError,
    cancel_task_draft,
    create_task_draft_from_intent,
    execute_task_draft,
    get_task_draft,
    preview_task_draft,
)


BATCH_TTL = timedelta(hours=1)


class AssistantBatchError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utc_now():
    return datetime.now(timezone.utc)


def _validated_intents(parsed):
    if not isinstance(parsed, dict):
        raise AssistantBatchError("Parsed batch result is required.")

    intents = parsed.get("intents")
    if not isinstance(intents, list) or not intents:
        raise AssistantBatchError("At least one parsed task is required.")

    if len(intents) > MAX_BATCH_TASKS:
        raise AssistantBatchError(
            f"A maximum of {MAX_BATCH_TASKS} tasks can be stored in one batch."
        )

    validated = []
    for index, intent in enumerate(intents):
        if not isinstance(intent, dict):
            raise AssistantBatchError(
                f"Task {index + 1} has an invalid intent structure."
            )

        action = intent.get("action")
        if action not in BATCH_CREATE_ACTIONS:
            raise AssistantBatchError(
                f"Task {index + 1} is not a supported create action."
            )

        arguments = intent.get("arguments")
        task = (arguments or {}).get("task") if isinstance(arguments, dict) else None
        if not isinstance(task, dict):
            raise AssistantBatchError(
                f"Task {index + 1} is missing its task payload."
            )

        validated.append(deepcopy(intent))

    return validated


def _public_item(item):
    return {
        "index": item["index"],
        "task_number": item["task_number"],
        "status": item["status"],
        "draft_id": item.get("draft_id"),
        "intent": deepcopy(item["intent"]),
    }


def create_task_batch(parsed, source_message=None):
    """Persist ordered parsed intents and activate only Task 1."""

    intents = _validated_intents(parsed)

    if source_message is not None and not isinstance(source_message, str):
        raise AssistantBatchError("source_message must be a string when provided.")

    now = _utc_now()
    items = []

    for index, intent in enumerate(intents):
        items.append(
            {
                "index": index,
                "task_number": index + 1,
                "status": "active" if index == 0 else "pending",
                "draft_id": None,
                "intent": intent,
            }
        )

    document = {
        "status": "in_progress",
        "current_index": 0,
        "total_tasks": len(items),
        "items": items,
        "source_message": source_message.strip() if source_message else None,
        "provider": parsed.get("provider", ""),
        "model": parsed.get("model", ""),
        "timezone": parsed.get("timezone", "UTC"),
        "fallback_used": bool(parsed.get("fallback_used", False)),
        "attempted_providers": list(parsed.get("attempted_providers") or []),
        "created_at": now,
        "updated_at": now,
        "expires_at": now + BATCH_TTL,
    }

    batch_id = insert_batch(document)
    document["_id"] = batch_id

    active_item = items[0]
    return {
        "batch_id": str(batch_id),
        "status": document["status"],
        "current_index": document["current_index"],
        "current_task_number": active_item["task_number"],
        "total_tasks": document["total_tasks"],
        "active_item": _public_item(active_item),
        "items": [_public_item(item) for item in items],
    }

def _active_item(batch):
    current_index = batch.get("current_index")
    items = batch.get("items") or []

    if not isinstance(current_index, int) or current_index < 0:
        raise AssistantBatchError("Batch current_index is invalid.", 500)

    item = next(
        (
            value
            for value in items
            if value.get("index") == current_index
        ),
        None,
    )

    if item is None or item.get("status") != "active":
        raise AssistantBatchError(
            "The batch has no valid active task.",
            409,
        )

    return item


def _active_task_response(batch, item, draft):
    return {
        "batch_id": str(batch["_id"]),
        "batch_status": batch.get("status"),
        "current_index": batch.get("current_index"),
        "current_task_number": item.get("task_number"),
        "total_tasks": batch.get("total_tasks"),
        "item_status": item.get("status"),
        "draft": draft,
    }


def prepare_active_task(batch_id):
    """Create/reuse the existing assistant draft for the active batch item.

    Step 1C intentionally stops at review readiness. It does not execute the
    command and does not advance current_index to the next task.
    """

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    if batch.get("status") != "in_progress":
        raise AssistantBatchError(
            "This assistant task batch is no longer active.",
            409,
        )

    item = _active_item(batch)
    existing_draft_id = item.get("draft_id")

    if existing_draft_id:
        try:
            draft = get_task_draft(existing_draft_id)
        except AssistantDraftError as error:
            raise AssistantBatchError(
                "The active task draft was not found or expired.",
                409,
            ) from error
        return _active_task_response(batch, item, draft)

    try:
        draft = create_task_draft_from_intent(
            item.get("intent"),
            timezone_name=batch.get("timezone") or "UTC",
            provider=batch.get("provider") or "batch",
            model=batch.get("model") or "",
            batch_id=str(batch["_id"]),
            batch_index=item["index"],
        )
    except AssistantDraftError as error:
        raise AssistantBatchError(
            error.message,
            error.status_code,
        ) from error

    now = _utc_now()
    updated = attach_draft_to_active_item(
        str(batch["_id"]),
        item["index"],
        draft["draft_id"],
        now,
        now + BATCH_TTL,
    )

    if updated is None:
        # A concurrent/retry request may have attached the draft first.
        # Reload and return the winning draft rather than advancing anything.
        latest = find_batch(str(batch["_id"]))
        if latest is not None:
            latest_item = _active_item(latest)
            winner_id = latest_item.get("draft_id")
            if winner_id:
                winner = get_task_draft(winner_id)
                return _active_task_response(
                    latest,
                    latest_item,
                    winner,
                )

        raise AssistantBatchError(
            "Could not attach the active task draft to the batch.",
            409,
        )

    updated_item = _active_item(updated)
    return _active_task_response(
        updated,
        updated_item,
        draft,
    )


def continue_active_task(
    batch_id,
    message,
    api_key=None,
    credentials=None,
):
    """Apply one follow-up answer to the active batch task.

    Step 1D keeps the batch pinned to the same active task. It reuses the
    existing single-task draft workflow for slot filling, validation, duplicate
    checks, and review readiness. It never executes a command and never
    advances current_index.
    """

    if not isinstance(message, str) or not message.strip():
        raise AssistantBatchError(
            "A non-empty follow-up message is required.",
            400,
        )

    # Ensure the active item has exactly one draft. This is idempotent.
    prepared = prepare_active_task(batch_id)
    draft = prepared.get("draft") or {}
    draft_id = draft.get("draft_id")

    if not draft_id:
        raise AssistantBatchError(
            "The active task has no assistant draft.",
            409,
        )

    # A review-ready task is frozen until the explicit Confirm/Cancel step.
    if draft.get("status") in {"ready", "duplicate_review"}:
        return prepared

    if draft.get("status") != "needs_input":
        raise AssistantBatchError(
            "The active task is not waiting for follow-up information.",
            409,
        )

    try:
        continued = preview_task_draft(
            message.strip(),
            timezone_name=draft.get("timezone") or "UTC",
            api_key=api_key,
            credentials=credentials,
            draft_id=draft_id,
        )
    except AssistantDraftError as error:
        raise AssistantBatchError(
            error.message,
            error.status_code,
        ) from error

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    item = _active_item(batch)

    # Defensive invariant: Step 1D must never switch drafts/tasks.
    if str(item.get("draft_id") or "") != str(draft_id):
        raise AssistantBatchError(
            "The active batch task changed while processing the follow-up.",
            409,
        )

    return _active_task_response(
        batch,
        item,
        continued,
    )


def _resolved_batch_response(batch, resolved_task_number, resolution, result=None):
    current_index = batch.get("current_index")
    items = batch.get("items") or []
    active_item = None

    if isinstance(current_index, int):
        active_item = next(
            (
                item
                for item in items
                if item.get("index") == current_index
            ),
            None,
        )

    return {
        "batch_id": str(batch["_id"]),
        "batch_status": batch.get("status"),
        "resolved_task_number": resolved_task_number,
        "resolution": resolution,
        "result": result,
        "current_index": current_index,
        "current_task_number": (
            active_item.get("task_number")
            if active_item is not None
            else None
        ),
        "total_tasks": batch.get("total_tasks"),
        "active_item": (
            _public_item(active_item)
            if active_item is not None
            else None
        ),
        "all_done": batch.get("status") == "completed",
    }


def _prepare_next_task_after_resolution(response):
    """Prepare the newly active item without changing resolution semantics.

    Task execution/skip has already succeeded by the time this helper runs.
    Therefore a failure while preparing the next task must NOT make the caller
    believe the resolved task failed. The next item stays active and can be
    prepared idempotently by a retry.
    """

    response = dict(response)
    response["next_task"] = None
    response["next_task_error"] = None

    if response.get("all_done"):
        return response

    batch_id = response.get("batch_id")

    try:
        prepared = prepare_active_task(batch_id)
    except AssistantBatchError as error:
        response["next_task_error"] = {
            "message": error.message,
            "status_code": error.status_code,
        }
        return response

    response["next_task"] = prepared
    response["current_index"] = prepared.get("current_index")
    response["current_task_number"] = prepared.get("current_task_number")

    # Keep the outer active_item snapshot consistent with the draft that was
    # just attached by prepare_active_task().
    try:
        latest = find_batch(batch_id)
        if latest is not None:
            latest_item = _active_item(latest)
            response["active_item"] = _public_item(latest_item)
    except (AssistantBatchError, InvalidId, TypeError, ValueError):
        # next_task already contains the authoritative prepared draft. A
        # cosmetic refresh failure must not turn a successful resolution into
        # an error.
        pass

    return response


def _next_unresolved_item(batch, excluding_index=None):
    """Return the next task to work on.

    New/pending tasks always come before tasks explicitly deferred with
    "Skip for now". Once no pending tasks remain, deferred tasks are revisited
    in their original order.
    """

    items = batch.get("items") or []

    pending = sorted(
        (
            item
            for item in items
            if item.get("index") != excluding_index
            and item.get("status") == "pending"
        ),
        key=lambda item: item.get("index", 0),
    )
    if pending:
        return pending[0]

    deferred = sorted(
        (
            item
            for item in items
            if item.get("index") != excluding_index
            and item.get("status") == "deferred"
        ),
        key=lambda item: item.get("index", 0),
    )
    return deferred[0] if deferred else None


def _advance_resolved_item(
    batch,
    item,
    resolved_status,
    result=None,
):
    now = _utc_now()
    next_item = _next_unresolved_item(
        batch,
        excluding_index=item.get("index"),
    )
    next_index = next_item.get("index") if next_item is not None else None

    updated = resolve_active_item_and_advance(
        str(batch["_id"]),
        item["index"],
        item.get("draft_id"),
        resolved_status,
        now,
        now + BATCH_TTL,
        next_index=next_index,
        result=result,
    )

    if updated is not None:
        return updated

    # Retry/recovery path: another request may already have advanced the same
    # resolved item. Never advance a second time.
    latest = find_batch(str(batch["_id"]))
    if latest is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    latest_item = next(
        (
            value
            for value in (latest.get("items") or [])
            if value.get("index") == item["index"]
        ),
        None,
    )

    if latest_item is not None and latest_item.get("status") == resolved_status:
        return latest

    raise AssistantBatchError(
        "The active batch task changed before it could be resolved.",
        409,
    )


def confirm_active_task(
    batch_id,
    draft_id,
    duplicate_decision=None,
    candidate_id=None,
):
    """Confirm and execute only the currently active batch task.

    Execution must succeed before the batch advances. If execution fails, the
    current item remains active and Task 2 stays pending.
    """

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    if batch.get("status") != "in_progress":
        raise AssistantBatchError(
            "This assistant task batch is no longer active.",
            409,
        )

    item = _active_item(batch)
    active_draft_id = item.get("draft_id")

    if not isinstance(draft_id, str) or not draft_id.strip():
        raise AssistantBatchError("draft_id is required.", 400)

    if not active_draft_id:
        raise AssistantBatchError(
            "The active task has no assistant draft.",
            409,
        )

    if str(active_draft_id) != draft_id.strip():
        raise AssistantBatchError(
            "This confirmation no longer belongs to the active task.",
            409,
        )

    draft_id = draft_id.strip()

    try:
        draft = get_task_draft(draft_id)
    except AssistantDraftError as error:
        raise AssistantBatchError(error.message, error.status_code) from error

    status = draft.get("status")
    result = None

    if status == "executed":
        # Recovery after: command executed successfully, but the caller lost
        # the response before the batch document could advance.
        pass
    elif status in {"ready", "duplicate_review"}:
        try:
            result = execute_task_draft(
                draft_id,
                confirmed=True,
                duplicate_decision=duplicate_decision,
                candidate_id=candidate_id,
            )
        except AssistantDraftError as error:
            # A racing request may have executed the draft first. Recover only
            # if the persisted draft is now definitively executed.
            latest_draft = get_task_draft(draft_id)
            if latest_draft.get("status") != "executed":
                raise AssistantBatchError(
                    error.message,
                    error.status_code,
                ) from error
    else:
        raise AssistantBatchError(
            "The active task is not ready for confirmation.",
            409,
        )

    updated = _advance_resolved_item(
        batch,
        item,
        "executed",
        result=result,
    )

    response = _resolved_batch_response(
        updated,
        item.get("task_number"),
        "executed",
        result=result,
    )

    return _prepare_next_task_after_resolution(response)


def cancel_active_task(batch_id, draft_id):
    """Skip the currently active batch task without creating/updating a task."""

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    if batch.get("status") != "in_progress":
        raise AssistantBatchError(
            "This assistant task batch is no longer active.",
            409,
        )

    item = _active_item(batch)
    active_draft_id = item.get("draft_id")

    if not isinstance(draft_id, str) or not draft_id.strip():
        raise AssistantBatchError("draft_id is required.", 400)

    if not active_draft_id:
        raise AssistantBatchError(
            "The active task has no assistant draft.",
            409,
        )

    if str(active_draft_id) != draft_id.strip():
        raise AssistantBatchError(
            "This cancellation no longer belongs to the active task.",
            409,
        )

    draft_id = draft_id.strip()

    try:
        cancel_task_draft(draft_id)
    except AssistantDraftError as error:
        raise AssistantBatchError(
            error.message,
            error.status_code,
        ) from error

    updated = _advance_resolved_item(
        batch,
        item,
        "skipped",
    )

    response = _resolved_batch_response(
        updated,
        item.get("task_number"),
        "skipped",
    )

    return _prepare_next_task_after_resolution(response)


def defer_active_task(batch_id, draft_id):
    """Skip the current task for now while preserving its draft and answers."""

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    if batch.get("status") != "in_progress":
        raise AssistantBatchError(
            "This assistant task batch is no longer active.",
            409,
        )

    item = _active_item(batch)
    active_draft_id = item.get("draft_id")

    if not isinstance(draft_id, str) or not draft_id.strip():
        raise AssistantBatchError("draft_id is required.", 400)

    draft_id = draft_id.strip()

    if not active_draft_id or str(active_draft_id) != draft_id:
        raise AssistantBatchError(
            "This skip request no longer belongs to the active task.",
            409,
        )

    next_item = _next_unresolved_item(
        batch,
        excluding_index=item.get("index"),
    )
    if next_item is None:
        raise AssistantBatchError(
            "There are no other tasks to skip to. Continue or discard this task instead.",
            409,
        )

    now = _utc_now()
    updated = defer_active_item_and_activate(
        str(batch["_id"]),
        item["index"],
        draft_id,
        next_item["index"],
        now,
        now + BATCH_TTL,
    )

    if updated is None:
        raise AssistantBatchError(
            "The active task changed before it could be skipped for now.",
            409,
        )

    response = _resolved_batch_response(
        updated,
        item.get("task_number"),
        "deferred",
    )
    return _prepare_next_task_after_resolution(response)


def abort_task_batch(batch_id, draft_id):
    """Discard all unfinished tasks without touching already saved tasks."""

    try:
        batch = find_batch(batch_id)
    except (InvalidId, TypeError, ValueError) as error:
        raise AssistantBatchError("Invalid batch_id.", 400) from error

    if batch is None:
        raise AssistantBatchError(
            "Assistant task batch was not found or expired.",
            404,
        )

    if batch.get("status") != "in_progress":
        raise AssistantBatchError(
            "This assistant task batch is no longer active.",
            409,
        )

    item = _active_item(batch)
    active_draft_id = item.get("draft_id")

    if not isinstance(draft_id, str) or not draft_id.strip():
        raise AssistantBatchError("draft_id is required.", 400)

    draft_id = draft_id.strip()

    if not active_draft_id:
        raise AssistantBatchError(
            "The active task has no assistant draft.",
            409,
        )

    if str(active_draft_id) != draft_id:
        raise AssistantBatchError(
            "This discard request no longer belongs to the active task.",
            409,
        )

    unfinished_draft_ids = {
        str(value.get("draft_id"))
        for value in (batch.get("items") or [])
        if value.get("status") in {"active", "deferred"}
        and value.get("draft_id")
    }

    for unfinished_draft_id in unfinished_draft_ids:
        try:
            cancel_task_draft(unfinished_draft_id)
        except AssistantDraftError as error:
            raise AssistantBatchError(
                error.message,
                error.status_code,
            ) from error

    now = _utc_now()
    discarded_items = deepcopy(batch.get("items") or [])
    for value in discarded_items:
        if value.get("status") in {"active", "pending", "deferred"}:
            value["status"] = "discarded"
            value["resolved_at"] = now

    updated = abort_active_batch(
        str(batch["_id"]),
        item["index"],
        draft_id,
        discarded_items,
        now,
        now + BATCH_TTL,
    )

    if updated is None:
        latest = find_batch(str(batch["_id"]))
        if latest is not None and latest.get("status") == "aborted":
            updated = latest
        else:
            raise AssistantBatchError(
                "The active task changed before it could be discarded.",
                409,
            )

    return {
        "batch_id": str(updated["_id"]),
        "batch_status": updated.get("status"),
        "total_tasks": updated.get("total_tasks"),
        "discarded": True,
    }
