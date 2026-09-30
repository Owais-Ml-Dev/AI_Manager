from pathlib import Path
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup(path: Path, suffix: str) -> None:
    target = path.with_name(path.name + suffix)
    if not target.exists():
        shutil.copy2(path, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected block for {label}.")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python apply_backend_step1e_confirm_advance.py <backend_dir>"
        )

    backend = Path(sys.argv[1]).resolve()

    batch_service = backend / "src/modules/assistant/batches/service.py"
    batch_repo = backend / "src/modules/assistant/batches/repository.py"
    draft_service = backend / "src/modules/assistant/drafts/service.py"
    draft_repo = backend / "src/modules/assistant/drafts/repository.py"
    test_path = backend / "tests/test_assistant_batch_confirmation.py"

    for path in (batch_service, batch_repo, draft_service, draft_repo):
        if not path.exists():
            raise RuntimeError(f"Missing expected file: {path}")

    # -------------------------------------------------------------
    # BATCH REPOSITORY: atomic resolve + advance
    # -------------------------------------------------------------
    text = read(batch_repo)
    if "def resolve_active_item_and_advance(" not in text:
        backup(batch_repo, ".before_step1e.bak")
        text = text.rstrip() + r'''


def resolve_active_item_and_advance(
    batch_id,
    item_index,
    draft_id,
    resolved_status,
    resolved_at,
    expires_at,
    has_next,
    result=None,
):
    """Atomically resolve the current item and activate the next one.

    The batch document is the sequencing authority. The filter guarantees that
    only the still-active item at current_index can be resolved. This prevents
    retries from skipping multiple tasks.
    """

    db = get_db()

    if resolved_status not in {"executed", "skipped"}:
        raise ValueError("resolved_status must be executed or skipped")

    set_fields = {
        f"items.{item_index}.status": resolved_status,
        f"items.{item_index}.resolved_at": resolved_at,
        "updated_at": resolved_at,
        "expires_at": expires_at,
    }

    if result is not None:
        set_fields[f"items.{item_index}.result"] = result

    next_index = item_index + 1

    if has_next:
        set_fields["current_index"] = next_index
        set_fields[f"items.{next_index}.status"] = "active"
    else:
        set_fields["status"] = "completed"
        set_fields["current_index"] = None

    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            f"items.{item_index}.status": "active",
            f"items.{item_index}.draft_id": str(draft_id),
        },
        {"$set": set_fields},
        return_document=ReturnDocument.AFTER,
    )
'''
        write(batch_repo, text)

    # -------------------------------------------------------------
    # DRAFT REPOSITORY: safe cancellation
    # -------------------------------------------------------------
    text = read(draft_repo)
    if "def cancel_draft(" not in text:
        backup(draft_repo, ".before_step1e.bak")
        text = text.rstrip() + r'''


def cancel_draft(draft_id, allowed_statuses, cancelled_at):
    """Atomically cancel a non-executing, non-executed draft."""

    db = get_db()
    return db.assistant_drafts.find_one_and_update(
        {
            "_id": ObjectId(draft_id),
            "status": {"$in": list(allowed_statuses)},
        },
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": cancelled_at,
                "updated_at": cancelled_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
'''
        write(draft_repo, text)

    # -------------------------------------------------------------
    # DRAFT SERVICE: expose deterministic cancellation
    # -------------------------------------------------------------
    text = read(draft_service)
    if "cancel_draft," not in text:
        backup(draft_service, ".before_step1e.bak")
        old = '''from src.modules.assistant.drafts.repository import (\n    claim_draft,\n    find_draft,\n    insert_draft,\n    mark_executed,\n    release_claim,\n    update_draft,\n)\n'''
        new = '''from src.modules.assistant.drafts.repository import (\n    cancel_draft,\n    claim_draft,\n    find_draft,\n    insert_draft,\n    mark_executed,\n    release_claim,\n    update_draft,\n)\n'''
        text = replace_once(text, old, new, "draft repository import")

    if "def cancel_task_draft(" not in text:
        function = r'''


def cancel_task_draft(draft_id):
    """Cancel a server-owned draft without executing its command.

    Cancellation is idempotent for an already-cancelled draft, but it never
    cancels an executing or executed draft.
    """

    draft = find_draft(draft_id)
    if draft is None:
        raise AssistantDraftError(
            "Assistant draft was not found or expired.",
            404,
        )

    status = draft.get("status")
    if status == "cancelled":
        return _response(draft)
    if status in {"executing", "executed"}:
        raise AssistantDraftError(
            "An executing or executed draft cannot be cancelled.",
            409,
        )

    allowed = {
        "collecting",
        "needs_input",
        "needs_target_selection",
        "ready",
        "duplicate_review",
    }

    if status not in allowed:
        raise AssistantDraftError(
            "This assistant draft cannot be cancelled in its current state.",
            409,
        )

    cancelled = cancel_draft(
        draft_id,
        allowed,
        _utc_now(),
    )

    if cancelled is None:
        latest = find_draft(draft_id)
        if latest is not None and latest.get("status") == "cancelled":
            return _response(latest)
        raise AssistantDraftError(
            "This assistant draft changed while it was being cancelled.",
            409,
        )

    return _response(cancelled)
'''
        # Put cancellation immediately before execution for readability.
        marker = "\ndef execute_task_draft(\n"
        if marker not in text:
            raise RuntimeError("Could not find execute_task_draft marker.")
        text = text.replace(marker, function + marker, 1)
        write(draft_service, text)

    # -------------------------------------------------------------
    # BATCH SERVICE: confirm/cancel + advance
    # -------------------------------------------------------------
    text = read(batch_service)
    backup(batch_service, ".before_step1e.bak")

    old_repo_import = '''from src.modules.assistant.batches.repository import (\n    attach_draft_to_active_item,\n    find_batch,\n    insert_batch,\n)\n'''
    new_repo_import = '''from src.modules.assistant.batches.repository import (\n    attach_draft_to_active_item,\n    find_batch,\n    insert_batch,\n    resolve_active_item_and_advance,\n)\n'''
    if "resolve_active_item_and_advance," not in text:
        text = replace_once(text, old_repo_import, new_repo_import, "batch repository import")

    old_draft_import = '''from src.modules.assistant.drafts.service import (\n    AssistantDraftError,\n    create_task_draft_from_intent,\n    get_task_draft,\n    preview_task_draft,\n)\n'''
    new_draft_import = '''from src.modules.assistant.drafts.service import (\n    AssistantDraftError,\n    cancel_task_draft,\n    create_task_draft_from_intent,\n    execute_task_draft,\n    get_task_draft,\n    preview_task_draft,\n)\n'''
    if "execute_task_draft," not in text:
        text = replace_once(text, old_draft_import, new_draft_import, "draft service import")

    if "def confirm_active_task(" not in text:
        functions = r'''


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


def _advance_resolved_item(
    batch,
    item,
    resolved_status,
    result=None,
):
    now = _utc_now()
    has_next = item["index"] + 1 < batch.get("total_tasks", 0)

    updated = resolve_active_item_and_advance(
        str(batch["_id"]),
        item["index"],
        item.get("draft_id"),
        resolved_status,
        now,
        now + BATCH_TTL,
        has_next,
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

    return _resolved_batch_response(
        updated,
        item.get("task_number"),
        "executed",
        result=result,
    )


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

    return _resolved_batch_response(
        updated,
        item.get("task_number"),
        "skipped",
    )
'''
        text = text.rstrip() + functions + "\n"

    write(batch_service, text)

    # -------------------------------------------------------------
    # TESTS
    # -------------------------------------------------------------
    test_text = r'''"""Step 1E: confirm/cancel Task 1 and advance exactly once."""

import pytest
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
    cancel_active_task,
    confirm_active_task,
    continue_active_task,
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
        _parsed(*[_intent(title) for title in titles]),
        source_message=" and ".join(titles),
    )


def _make_review_ready(batch_id):
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    return continue_active_task(batch_id, "2")


def test_confirm_executes_task_one_then_activates_task_two():
    batch = _batch("Gym", "Call John")
    ready = _make_review_ready(batch["batch_id"])
    assert ready["draft"]["status"] == "ready"

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["resolved_task_number"] == 1
    assert result["batch_status"] == "in_progress"
    assert result["current_task_number"] == 2
    assert result["all_done"] is False

    db = get_db()
    assert db.tasks.count_documents({"title": "Gym"}) == 1

    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 1
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][1]["draft_id"] is None


def test_cancel_skips_task_one_without_execution_and_activates_task_two():
    batch = _batch("Gym", "Call John")
    ready = _make_review_ready(batch["batch_id"])
    draft_id = ready["draft"]["draft_id"]

    result = cancel_active_task(
        batch["batch_id"],
        draft_id,
    )

    assert result["resolution"] == "skipped"
    assert result["current_task_number"] == 2

    db = get_db()
    assert db.tasks.count_documents({}) == 0
    draft = db.assistant_drafts.find_one({"_id": ObjectId(draft_id)})
    assert draft["status"] == "cancelled"

    stored = db.assistant_task_batches.find_one({})
    assert stored["items"][0]["status"] == "skipped"
    assert stored["items"][1]["status"] == "active"


def test_confirm_not_ready_does_not_execute_or_advance():
    batch = _batch("Gym", "Call John")
    prepared = prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        confirm_active_task(
            batch["batch_id"],
            prepared["draft"]["draft_id"],
        )

    assert exc.value.status_code == 409

    db = get_db()
    assert db.tasks.count_documents({}) == 0
    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "pending"


def test_last_confirm_marks_batch_completed():
    batch = _batch("Gym")
    ready = _make_review_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["batch_status"] == "completed"
    assert result["current_index"] is None
    assert result["current_task_number"] is None
    assert result["active_item"] is None
    assert result["all_done"] is True

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["status"] == "completed"
    assert stored["current_index"] is None
    assert stored["items"][0]["status"] == "executed"


def test_last_cancel_marks_batch_completed_without_creating_task():
    batch = _batch("Gym")
    prepared = prepare_active_task(batch["batch_id"])

    result = cancel_active_task(
        batch["batch_id"],
        prepared["draft"]["draft_id"],
    )

    assert result["resolution"] == "skipped"
    assert result["batch_status"] == "completed"
    assert result["all_done"] is True
    assert get_db().tasks.count_documents({}) == 0


def test_confirmed_task_cannot_advance_batch_twice():
    batch = _batch("Gym", "Call John", "Pay Bill")
    ready = _make_review_ready(batch["batch_id"])
    old_draft_id = ready["draft"]["draft_id"]

    first = confirm_active_task(
        batch["batch_id"],
        old_draft_id,
    )
    assert first["current_task_number"] == 2

    # Even if Task 2 is prepared immediately, a late double-tap carrying the
    # old Task-1 draft id must never confirm Task 2.
    prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        confirm_active_task(
            batch["batch_id"],
            old_draft_id,
        )

    assert exc.value.status_code == 409

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["current_index"] == 1
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][2]["status"] == "pending"
    assert get_db().tasks.count_documents({"title": "Gym"}) == 1
'''

    write(test_path, test_text)

    # Basic syntax verification using the current interpreter.
    import py_compile
    for path in (batch_service, batch_repo, draft_service, draft_repo, test_path):
        py_compile.compile(str(path), doraise=True)

    print("Step 1E applied successfully.")
    print("Syntax check: passed")
    print("Added confirmation/cancellation + single-step batch advancement.")


if __name__ == "__main__":
    main()
