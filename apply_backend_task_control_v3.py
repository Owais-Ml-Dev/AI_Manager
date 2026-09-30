from pathlib import Path
import py_compile
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def backup(path: Path) -> None:
    target = path.with_name(path.name + '.before_task_control_v2.bak')
    if not target.exists():
        shutil.copy2(path, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f'Could not find expected block for {label}.')
    return text.replace(old, new, 1)


def replace_function(text: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise RuntimeError(f'Could not find start of {label}.')

    end = text.find(end_marker, start)
    if end == -1:
        # Older project state: the requested anchor may not exist yet.
        # Fall back to the next top-level function, or EOF when this is the
        # final function in the file.
        next_def = text.find('\ndef ', start + len(start_marker))
        end = len(text) if next_def == -1 else next_def + 1

    return text[:start] + replacement.rstrip() + '\n\n\n' + text[end:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python apply_backend_task_control_v3.py <backend_dir>')

    backend = Path(sys.argv[1]).resolve()
    assistant = backend / 'src/modules/assistant'
    repo = assistant / 'batches/repository.py'
    service = assistant / 'batches/service.py'
    controller = assistant / 'controller.py'
    routes = assistant / 'routes.py'
    test = backend / 'tests/test_assistant_task_control_v2.py'

    for path in (repo, service, controller, routes):
        if not path.exists():
            raise RuntimeError(f'Missing expected file: {path}')
        backup(path)

    # ------------------------------------------------------------------
    # 1) Repository: generalized advancement + defer-for-now primitive.
    # ------------------------------------------------------------------
    repo_text = read(repo)

    # Step 3A is self-contained. The earlier Exit & Discard patch may not
    # have been applied yet, so add the atomic whole-batch abort primitive
    # when it is missing.
    if 'def abort_active_batch(' not in repo_text:
        repo_text = repo_text.rstrip() + r'''


def abort_active_batch(
    batch_id,
    item_index,
    draft_id,
    discarded_items,
    aborted_at,
    expires_at,
):
    """Abort all unfinished work if this draft is still the active one."""

    db = get_db()
    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            f"items.{item_index}.status": "active",
            f"items.{item_index}.draft_id": str(draft_id),
        },
        {
            "$set": {
                "status": "aborted",
                "current_index": None,
                "items": discarded_items,
                "aborted_at": aborted_at,
                "updated_at": aborted_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
'''

    new_resolve = r'''def resolve_active_item_and_advance(
    batch_id,
    item_index,
    draft_id,
    resolved_status,
    resolved_at,
    expires_at,
    next_index=None,
    result=None,
):
    """Atomically resolve the current item and activate the next unresolved item.

    ``next_index`` may point forward or backward. This is required when a task
    was previously deferred with "Skip for now" and needs to be revisited after
    the still-pending tasks have been reviewed.
    """

    db = get_db()

    if resolved_status not in {"executed", "skipped"}:
        raise ValueError("resolved_status must be executed or skipped")

    if next_index is not None:
        if not isinstance(next_index, int) or next_index < 0:
            raise ValueError("next_index must be a non-negative integer or None")
        if next_index == item_index:
            raise ValueError("next_index cannot point to the item being resolved")

    set_fields = {
        f"items.{item_index}.status": resolved_status,
        f"items.{item_index}.resolved_at": resolved_at,
        "updated_at": resolved_at,
        "expires_at": expires_at,
    }

    if result is not None:
        set_fields[f"items.{item_index}.result"] = result

    query = {
        "_id": ObjectId(batch_id),
        "status": "in_progress",
        "current_index": item_index,
        f"items.{item_index}.status": "active",
        f"items.{item_index}.draft_id": str(draft_id),
    }

    if next_index is not None:
        query[f"items.{next_index}.status"] = {"$in": ["pending", "deferred"]}
        set_fields["current_index"] = next_index
        set_fields[f"items.{next_index}.status"] = "active"
    else:
        set_fields["status"] = "completed"
        set_fields["current_index"] = None

    return db.assistant_task_batches.find_one_and_update(
        query,
        {"$set": set_fields},
        return_document=ReturnDocument.AFTER,
    )'''

    repo_text = replace_function(
        repo_text,
        'def resolve_active_item_and_advance(',
        'def abort_active_batch(',
        new_resolve,
        'resolve_active_item_and_advance',
    )

    if 'def defer_active_item_and_activate(' not in repo_text:
        defer_repo = r'''def defer_active_item_and_activate(
    batch_id,
    item_index,
    draft_id,
    next_index,
    deferred_at,
    expires_at,
):
    """Defer the current task without cancelling its draft, then activate another.

    The preserved draft is the key difference between Skip for Now and Discard.
    """

    db = get_db()

    if not isinstance(next_index, int) or next_index < 0 or next_index == item_index:
        raise ValueError("next_index must identify another batch item")

    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            f"items.{item_index}.status": "active",
            f"items.{item_index}.draft_id": str(draft_id),
            f"items.{next_index}.status": {"$in": ["pending", "deferred"]},
        },
        {
            "$set": {
                f"items.{item_index}.status": "deferred",
                f"items.{item_index}.deferred_at": deferred_at,
                f"items.{next_index}.status": "active",
                "current_index": next_index,
                "updated_at": deferred_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


'''
        marker = 'def abort_active_batch('
        idx = repo_text.find(marker)
        if idx == -1:
            raise RuntimeError('Could not find abort_active_batch repository anchor.')
        repo_text = repo_text[:idx] + defer_repo + repo_text[idx:]

    write(repo, repo_text)

    # ------------------------------------------------------------------
    # 2) Service: choose pending tasks first, then deferred tasks.
    # ------------------------------------------------------------------
    service_text = read(service)

    # The previous Exit & Discard patch was optional. Add its backend service
    # primitive here when absent so Step 3A can be applied directly.
    if 'abort_active_batch,' not in service_text:
        service_text = replace_once(
            service_text,
            'from src.modules.assistant.batches.repository import (\n'
            '    attach_draft_to_active_item,\n',
            'from src.modules.assistant.batches.repository import (\n'
            '    abort_active_batch,\n'
            '    attach_draft_to_active_item,\n',
            'batch repository abort import',
        )

    if 'def abort_task_batch(' not in service_text:
        service_text = service_text.rstrip() + r'''


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
'''

    old_import = '''from src.modules.assistant.batches.repository import (\n    abort_active_batch,\n    attach_draft_to_active_item,\n    find_batch,\n    insert_batch,\n    resolve_active_item_and_advance,\n)\n'''
    new_import = '''from src.modules.assistant.batches.repository import (\n    abort_active_batch,\n    attach_draft_to_active_item,\n    defer_active_item_and_activate,\n    find_batch,\n    insert_batch,\n    resolve_active_item_and_advance,\n)\n'''
    if 'defer_active_item_and_activate,' not in service_text:
        service_text = replace_once(service_text, old_import, new_import, 'batch repository imports')

    if 'def _next_unresolved_item(' not in service_text:
        anchor = 'def _advance_resolved_item(\n'
        idx = service_text.find(anchor)
        if idx == -1:
            raise RuntimeError('Could not find _advance_resolved_item service anchor.')
        helper = r'''def _next_unresolved_item(batch, excluding_index=None):
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


'''
        service_text = service_text[:idx] + helper + service_text[idx:]

    old_advance_start = service_text.find('def _advance_resolved_item(')
    old_advance_end = service_text.find('def confirm_active_task(', old_advance_start)
    if old_advance_start == -1 or old_advance_end == -1:
        raise RuntimeError('Could not isolate _advance_resolved_item.')

    new_advance = r'''def _advance_resolved_item(
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
    )'''

    service_text = (
        service_text[:old_advance_start]
        + new_advance.rstrip()
        + '\n\n\n'
        + service_text[old_advance_end:]
    )

    if 'def defer_active_task(' not in service_text:
        marker = 'def abort_task_batch('
        idx = service_text.find(marker)
        if idx == -1:
            raise RuntimeError('Could not find abort_task_batch service anchor.')

        defer_service = r'''def defer_active_task(batch_id, draft_id):
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


'''
        service_text = service_text[:idx] + defer_service + service_text[idx:]

    # Abort must include deferred tasks and cancel every preserved unfinished draft.
    old_abort_cancel = '''    # Cancel the server-owned draft first. This guarantees that an unfinished\n    # command can never be executed after Exit & Discard succeeds.\n    try:\n        cancel_task_draft(draft_id)\n    except AssistantDraftError as error:\n        raise AssistantBatchError(\n            error.message,\n            error.status_code,\n        ) from error\n\n    now = _utc_now()\n    discarded_items = deepcopy(batch.get("items") or [])\n    for value in discarded_items:\n        if value.get("status") in {"active", "pending"}:\n            value["status"] = "discarded"\n            value["resolved_at"] = now\n'''
    new_abort_cancel = '''    # Cancel every preserved unfinished draft. Deferred tasks keep their draft\n    # while the batch is active, so discarding the remaining batch must cancel\n    # those drafts too. Already executed/skipped tasks are intentionally left\n    # untouched.\n    unfinished_draft_ids = {\n        str(value.get("draft_id"))\n        for value in (batch.get("items") or [])\n        if value.get("status") in {"active", "deferred"}\n        and value.get("draft_id")\n    }\n\n    for unfinished_draft_id in unfinished_draft_ids:\n        try:\n            cancel_task_draft(unfinished_draft_id)\n        except AssistantDraftError as error:\n            raise AssistantBatchError(\n                error.message,\n                error.status_code,\n            ) from error\n\n    now = _utc_now()\n    discarded_items = deepcopy(batch.get("items") or [])\n    for value in discarded_items:\n        if value.get("status") in {"active", "pending", "deferred"}:\n            value["status"] = "discarded"\n            value["resolved_at"] = now\n'''
    if old_abort_cancel in service_text:
        service_text = service_text.replace(old_abort_cancel, new_abort_cancel, 1)
    elif 'unfinished_draft_ids = {' not in service_text:
        raise RuntimeError('Could not find abort draft-cancellation block.')

    write(service, service_text)

    # ------------------------------------------------------------------
    # 3) HTTP: POST /task-batch/<id>/defer
    # ------------------------------------------------------------------
    controller_text = read(controller)

    if '    abort_task_batch,' not in controller_text:
        controller_text = replace_once(
            controller_text,
            'from src.modules.assistant.batches.service import (\n'
            '    AssistantBatchError,\n',
            'from src.modules.assistant.batches.service import (\n'
            '    AssistantBatchError,\n'
            '    abort_task_batch,\n',
            'controller batch abort import',
        )

    if 'def abort_task_batch_controller(' not in controller_text:
        abort_controller = r'''def abort_task_batch_controller(batch_id):
    """Discard all unfinished tasks in the active batch."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    draft_id = data.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({
            "success": False,
            "message": "draft_id is required.",
        }), 400

    try:
        result = abort_task_batch(batch_id, draft_id.strip())
    except AssistantBatchError as error:
        return _batch_error_response(error)

    return jsonify({"success": True, "data": result}), 200


'''
        anchor = 'def cancel_task_batch_controller(batch_id):\n'
        idx = controller_text.find(anchor)
        if idx == -1:
            raise RuntimeError('Could not find batch cancel controller anchor.')
        controller_text = controller_text[:idx] + abort_controller + controller_text[idx:]

    if 'defer_active_task,' not in controller_text:
        controller_text = replace_once(
            controller_text,
            '    continue_active_task,\n',
            '    continue_active_task,\n    defer_active_task,\n',
            'controller service import',
        )

    if 'def defer_task_batch_controller(' not in controller_text:
        anchor = 'def abort_task_batch_controller(batch_id):\n'
        idx = controller_text.find(anchor)
        if idx == -1:
            raise RuntimeError('Could not find abort controller anchor.')
        defer_controller = r'''def defer_task_batch_controller(batch_id):
    """Skip the current task for now, preserving its draft for a later revisit."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    draft_id = data.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({
            "success": False,
            "message": "draft_id is required.",
        }), 400

    try:
        result = defer_active_task(batch_id, draft_id.strip())
    except AssistantBatchError as error:
        return _batch_error_response(error)

    return jsonify({"success": True, "data": result}), 200


'''
        controller_text = controller_text[:idx] + defer_controller + controller_text[idx:]

    # Existing /cancel is now explicitly permanent discard-current semantics.
    controller_text = controller_text.replace(
        '    """Skip only the currently active batch task and prepare the next one."""',
        '    """Discard only the currently active batch task and prepare the next one."""',
        1,
    )
    write(controller, controller_text)

    routes_text = read(routes)

    if '    abort_task_batch_controller,' not in routes_text:
        routes_text = replace_once(
            routes_text,
            'from src.modules.assistant.controller import (\n'
            '    assistant_chat_controller,\n',
            'from src.modules.assistant.controller import (\n'
            '    assistant_chat_controller,\n'
            '    abort_task_batch_controller,\n',
            'route abort controller import',
        )

    if '/task-batch/<batch_id>/abort' not in routes_text:
        abort_anchor = '''assistant_bp.route("/task-batch/<batch_id>/cancel", methods=["POST"])(\n    cancel_task_batch_controller\n)\n'''
        abort_addition = abort_anchor + '''assistant_bp.route("/task-batch/<batch_id>/abort", methods=["POST"])(\n    abort_task_batch_controller\n)\n'''
        routes_text = replace_once(
            routes_text,
            abort_anchor,
            abort_addition,
            'batch abort route',
        )

    if 'defer_task_batch_controller,' not in routes_text:
        routes_text = replace_once(
            routes_text,
            '    continue_task_batch_controller,\n',
            '    continue_task_batch_controller,\n    defer_task_batch_controller,\n',
            'route controller import',
        )

    if '/task-batch/<batch_id>/defer' not in routes_text:
        anchor = '''assistant_bp.route("/task-batch/<batch_id>/cancel", methods=["POST"])(\n    cancel_task_batch_controller\n)\n'''
        addition = anchor + '''assistant_bp.route("/task-batch/<batch_id>/defer", methods=["POST"])(\n    defer_task_batch_controller\n)\n'''
        routes_text = replace_once(routes_text, anchor, addition, 'defer route')
    write(routes, routes_text)

    # ------------------------------------------------------------------
    # 4) Tests: preserve draft, revisit deferred tasks, abort remaining.
    # ------------------------------------------------------------------
    test.write_text(r'''"""Task-control V2: skip-for-now, discard-current, discard-remaining."""

import pytest
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
    abort_task_batch,
    cancel_active_task,
    create_task_batch,
    defer_active_task,
    prepare_active_task,
)


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
        {
            "provider": "groq",
            "model": "test-model",
            "timezone": "UTC",
            "fallback_used": False,
            "attempted_providers": ["groq"],
            "intents": [_intent(title) for title in titles],
        },
        source_message=" and ".join(titles),
    )


def test_skip_for_now_preserves_draft_and_activates_next_task():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    result = defer_active_task(batch["batch_id"], first_draft_id)

    assert result["resolution"] == "deferred"
    assert result["resolved_task_number"] == 1
    assert result["current_task_number"] == 2
    assert result["next_task"]["current_task_number"] == 2

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["items"][0]["status"] == "deferred"
    assert stored["items"][0]["draft_id"] == first_draft_id
    assert stored["items"][1]["status"] == "active"


def test_deferred_task_is_revisited_after_pending_tasks_are_resolved():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    second = defer_active_task(batch["batch_id"], first_draft_id)["next_task"]
    third = cancel_active_task(
        batch["batch_id"],
        second["draft"]["draft_id"],
    )["next_task"]

    revisited = cancel_active_task(
        batch["batch_id"],
        third["draft"]["draft_id"],
    )["next_task"]

    assert revisited["current_task_number"] == 1
    assert revisited["draft"]["draft_id"] == first_draft_id

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "skipped"
    assert stored["items"][2]["status"] == "skipped"


def test_discard_remaining_also_discards_previously_deferred_tasks():
    batch = _batch("Task A", "Task B", "Task C")
    first = prepare_active_task(batch["batch_id"])
    first_draft_id = first["draft"]["draft_id"]

    second = defer_active_task(batch["batch_id"], first_draft_id)["next_task"]
    abort_task_batch(batch["batch_id"], second["draft"]["draft_id"])

    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["status"] == "aborted"
    assert stored["current_index"] is None
    assert [item["status"] for item in stored["items"]] == [
        "discarded",
        "discarded",
        "discarded",
    ]

    first_draft = get_db().assistant_drafts.find_one({"draft_id": first_draft_id})
    assert first_draft is not None
    assert first_draft["status"] == "cancelled"


def test_single_task_cannot_skip_for_now_without_destroying_state():
    batch = _batch("Only Task")
    active = prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as error:
        defer_active_task(batch["batch_id"], active["draft"]["draft_id"])

    assert error.value.status_code == 409
    stored = get_db().assistant_task_batches.find_one(
        {"_id": ObjectId(batch["batch_id"])}
    )
    assert stored["status"] == "in_progress"
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
''', encoding='utf-8')

    for path in (repo, service, controller, routes, test):
        py_compile.compile(str(path), doraise=True)

    print('Backend task-control V3 applied successfully.')
    print('Added: Skip for Now (deferred draft), deferred-task revisit, discard remaining.')
    print('Existing /cancel remains permanent discard-current semantics.')
    print('Syntax check: passed')


if __name__ == '__main__':
    main()
