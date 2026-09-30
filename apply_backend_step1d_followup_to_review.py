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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python apply_backend_step1d_followup_to_review.py <backend_dir>"
        )

    backend = Path(sys.argv[1]).resolve()
    service_path = backend / "src/modules/assistant/batches/service.py"
    test_path = backend / "tests/test_assistant_batch_followups.py"

    if not service_path.exists():
        raise RuntimeError(f"Missing expected Step 1C file: {service_path}")

    text = read(service_path)

    # Step 1D requires the Step 1C bridge to already exist.
    required_markers = [
        "def prepare_active_task(",
        "create_task_draft_from_intent",
        "get_task_draft",
    ]
    for marker in required_markers:
        if marker not in text:
            raise RuntimeError(
                f"Step 1C prerequisite not found in {service_path}: {marker}"
            )

    backup(service_path, ".before_step1d.bak")

    old_import = '''from src.modules.assistant.drafts.service import (\n    AssistantDraftError,\n    create_task_draft_from_intent,\n    get_task_draft,\n)\n'''
    new_import = '''from src.modules.assistant.drafts.service import (\n    AssistantDraftError,\n    create_task_draft_from_intent,\n    get_task_draft,\n    preview_task_draft,\n)\n'''

    if "preview_task_draft," not in text:
        if old_import not in text:
            raise RuntimeError(
                "Could not find the expected Step 1C draft-service import block."
            )
        text = text.replace(old_import, new_import, 1)

    function_block = r'''


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
'''

    if "def continue_active_task(" not in text:
        text = text.rstrip() + function_block + "\n"

    write(service_path, text)

    test_text = r'''"""Step 1D: continue Task 1 until it becomes review-ready."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
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


def _intent(title, confirmed=True):
    collect = {}
    if confirmed:
        collect = {
            "task_type_confirmed": True,
            "selected_task_action": "create_recurring_task",
        }

    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": {"title": title},
            "collect": collect,
        },
    }


def _batch():
    return create_task_batch(
        _parsed(
            _intent("Gym"),
            _intent("Call John"),
        ),
        source_message="Create Gym and Call John.",
    )


def test_followup_moves_task_one_to_next_missing_field():
    batch = _batch()
    first = prepare_active_task(batch["batch_id"])
    assert first["draft"]["missing_fields"] == ["duration"]

    result = continue_active_task(
        batch["batch_id"],
        "1 Jan 2099 to 31 Jan 2099",
    )

    assert result["current_task_number"] == 1
    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["repeat"]


def test_followups_can_reach_review_without_advancing_task_two():
    batch = _batch()
    batch_id = batch["batch_id"]
    prepare_active_task(batch_id)

    result = continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    assert result["draft"]["missing_fields"] == ["repeat"]

    result = continue_active_task(batch_id, "Every day")
    assert result["draft"]["missing_fields"] == ["reminders.count"]

    result = continue_active_task(batch_id, "1")
    assert result["draft"]["missing_fields"] == ["reminders.window"]

    result = continue_active_task(batch_id, "7 am to 8 am")
    assert result["draft"]["missing_fields"] == [
        "reminders.window_reminder_count"
    ]

    result = continue_active_task(batch_id, "2")
    assert result["draft"]["status"] in {"ready", "duplicate_review"}
    assert result["draft"]["command"] is not None
    assert result["draft"]["command"]["requires_confirmation"] is True

    db = get_db()
    assert db.tasks.count_documents({}) == 0

    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][1]["status"] == "pending"
    assert stored["items"][1]["draft_id"] is None


def test_review_ready_task_ignores_extra_followup_and_stays_same_draft():
    batch = _batch()
    batch_id = batch["batch_id"]
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    ready = continue_active_task(batch_id, "2")

    repeated = continue_active_task(batch_id, "change the title")

    assert repeated["draft"]["draft_id"] == ready["draft"]["draft_id"]
    assert repeated["draft"]["status"] == ready["draft"]["status"]
    assert repeated["draft"]["command"] == ready["draft"]["command"]
    assert get_db().tasks.count_documents({}) == 0


def test_blank_followup_is_rejected_without_changing_batch():
    batch = _batch()
    prepare_active_task(batch["batch_id"])

    with pytest.raises(AssistantBatchError) as exc:
        continue_active_task(batch["batch_id"], "   ")

    assert exc.value.status_code == 400
    stored = get_db().assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][1]["status"] == "pending"
'''

    write(test_path, test_text)

    # Syntax-check exactly what was changed/created.
    import py_compile

    py_compile.compile(str(service_path), doraise=True)
    py_compile.compile(str(test_path), doraise=True)

    print("Step 1D applied successfully.")
    print(f"Updated: {service_path}")
    print(f"Created: {test_path}")
    print("Syntax check: passed")


if __name__ == "__main__":
    main()
