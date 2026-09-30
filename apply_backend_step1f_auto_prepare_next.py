from pathlib import Path
import shutil
import sys
import py_compile


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}")
    write(path, text.replace(old, new, 1))


def backup(path: Path, suffix: str) -> None:
    target = path.with_name(path.name + suffix)
    if not target.exists():
        shutil.copy2(path, target)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python apply_backend_step1f_auto_prepare_next.py <backend_dir>"
        )

    backend = Path(sys.argv[1]).resolve()
    if not (backend / "src").exists():
        raise RuntimeError(f"Backend src directory not found: {backend}")

    service = backend / "src/modules/assistant/batches/service.py"
    confirmation_test = backend / "tests/test_assistant_batch_confirmation.py"
    new_test = backend / "tests/test_assistant_batch_auto_prepare.py"

    for path in (service, confirmation_test):
        if not path.exists():
            raise RuntimeError(f"Required file not found: {path}")

    backup(service, ".before_step1f.bak")
    backup(confirmation_test, ".before_step1f.bak")

    helper_anchor = '''def _advance_resolved_item(\n    batch,\n    item,\n    resolved_status,\n    result=None,\n):\n'''

    helper = '''def _prepare_next_task_after_resolution(response):\n    \"\"\"Prepare the newly active item without changing resolution semantics.\n\n    Task execution/skip has already succeeded by the time this helper runs.\n    Therefore a failure while preparing the next task must NOT make the caller\n    believe the resolved task failed. The next item stays active and can be\n    prepared idempotently by a retry.\n    \"\"\"\n\n    response = dict(response)\n    response[\"next_task\"] = None\n    response[\"next_task_error\"] = None\n\n    if response.get(\"all_done\"):\n        return response\n\n    batch_id = response.get(\"batch_id\")\n\n    try:\n        prepared = prepare_active_task(batch_id)\n    except AssistantBatchError as error:\n        response[\"next_task_error\"] = {\n            \"message\": error.message,\n            \"status_code\": error.status_code,\n        }\n        return response\n\n    response[\"next_task\"] = prepared\n    response[\"current_index\"] = prepared.get(\"current_index\")\n    response[\"current_task_number\"] = prepared.get(\"current_task_number\")\n\n    # Keep the outer active_item snapshot consistent with the draft that was\n    # just attached by prepare_active_task().\n    try:\n        latest = find_batch(batch_id)\n        if latest is not None:\n            latest_item = _active_item(latest)\n            response[\"active_item\"] = _public_item(latest_item)\n    except (AssistantBatchError, InvalidId, TypeError, ValueError):\n        # next_task already contains the authoritative prepared draft. A\n        # cosmetic refresh failure must not turn a successful resolution into\n        # an error.\n        pass\n\n    return response\n\n\n'''

    text = read(service)
    if "def _prepare_next_task_after_resolution(" not in text:
        if helper_anchor not in text:
            raise RuntimeError("Could not find Step 1E advancement anchor in service.py")
        text = text.replace(helper_anchor, helper + helper_anchor, 1)
        write(service, text)

    old_confirm_return = '''    return _resolved_batch_response(\n        updated,\n        item.get(\"task_number\"),\n        \"executed\",\n        result=result,\n    )\n\n\n'''
    new_confirm_return = '''    response = _resolved_batch_response(\n        updated,\n        item.get(\"task_number\"),\n        \"executed\",\n        result=result,\n    )\n\n    return _prepare_next_task_after_resolution(response)\n\n\n'''
    replace_once(service, old_confirm_return, new_confirm_return)

    old_cancel_return = '''    return _resolved_batch_response(\n        updated,\n        item.get(\"task_number\"),\n        \"skipped\",\n    )\n'''
    new_cancel_return = '''    response = _resolved_batch_response(\n        updated,\n        item.get(\"task_number\"),\n        \"skipped\",\n    )\n\n    return _prepare_next_task_after_resolution(response)\n'''
    replace_once(service, old_cancel_return, new_cancel_return)

    # Step 1E intentionally expected Task 2 to have no draft. Step 1F changes
    # that invariant: the next item is prepared immediately after resolution.
    old_assert = '''    assert stored[\"items\"][1][\"status\"] == \"active\"\n    assert stored[\"items\"][1][\"draft_id\"] is None\n'''
    new_assert = '''    assert stored[\"items\"][1][\"status\"] == \"active\"\n    assert stored[\"items\"][1][\"draft_id\"] == (\n        result[\"next_task\"][\"draft\"][\"draft_id\"]\n    )\n'''
    replace_once(confirmation_test, old_assert, new_assert)

    test_source = r'''"""Step 1F: resolve Task 1, then immediately prepare the next task."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
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


def _intent(title, *, complete=False):
    task = {"title": title}
    collect = {
        "task_type_confirmed": True,
        "selected_task_action": "create_recurring_task",
    }

    if complete:
        task.update(
            {
                "duration": {
                    "start_date": "2099-02-01",
                    "end_date": "2099-02-28",
                },
                "repeat": {
                    "type": "everyday",
                    "custom_dates": [],
                },
                "reminders": [
                    {
                        "start_time": "09:00",
                        "end_time": "10:00",
                        "count": 2,
                    }
                ],
            }
        )
        collect.update(
            {
                "window_count": 1,
                "confirmed_window_counts": 1,
            }
        )

    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": task,
            "collect": collect,
        },
    }


def _batch(second_complete=False):
    return create_task_batch(
        _parsed(
            _intent("Gym"),
            _intent("Call John", complete=second_complete),
        ),
        source_message="Create Gym and Call John.",
    )


def _make_first_ready(batch_id):
    prepare_active_task(batch_id)
    continue_active_task(batch_id, "1 Jan 2099 to 31 Jan 2099")
    continue_active_task(batch_id, "Every day")
    continue_active_task(batch_id, "1")
    continue_active_task(batch_id, "7 am to 8 am")
    return continue_active_task(batch_id, "2")


def test_confirm_immediately_prepares_task_two_and_returns_its_question():
    batch = _batch()
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["resolution"] == "executed"
    assert result["current_task_number"] == 2
    assert result["next_task_error"] is None

    next_task = result["next_task"]
    assert next_task is not None
    assert next_task["current_task_number"] == 2
    assert next_task["draft"]["status"] == "needs_input"
    assert next_task["draft"]["missing_fields"] == ["duration"]

    stored = get_db().assistant_task_batches.find_one({})
    assert stored["items"][0]["status"] == "executed"
    assert stored["items"][1]["status"] == "active"
    assert stored["items"][1]["draft_id"] == next_task["draft"]["draft_id"]


def test_cancel_immediately_prepares_task_two_without_creating_task_one():
    batch = _batch()
    prepared = prepare_active_task(batch["batch_id"])

    result = cancel_active_task(
        batch["batch_id"],
        prepared["draft"]["draft_id"],
    )

    assert result["resolution"] == "skipped"
    assert result["current_task_number"] == 2
    assert result["next_task"] is not None
    assert result["next_task"]["draft"]["missing_fields"] == ["duration"]
    assert get_db().tasks.count_documents({}) == 0


def test_fully_specified_task_two_is_immediately_ready_for_review():
    batch = _batch(second_complete=True)
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    next_task = result["next_task"]
    assert next_task is not None
    assert next_task["current_task_number"] == 2
    assert next_task["draft"]["status"] in {"ready", "duplicate_review"}
    assert next_task["draft"]["command"] is not None
    assert next_task["draft"]["command"]["requires_confirmation"] is True

    # Task 2 has only reached review. It has not been executed.
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0


def test_last_task_resolution_has_no_next_task():
    batch = create_task_batch(
        _parsed(_intent("Gym")),
        source_message="Create Gym.",
    )
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )

    assert result["all_done"] is True
    assert result["batch_status"] == "completed"
    assert result["next_task"] is None
    assert result["next_task_error"] is None


def test_explicit_prepare_after_auto_prepare_reuses_same_task_two_draft():
    batch = _batch()
    ready = _make_first_ready(batch["batch_id"])

    result = confirm_active_task(
        batch["batch_id"],
        ready["draft"]["draft_id"],
    )
    auto_draft_id = result["next_task"]["draft"]["draft_id"]

    repeated = prepare_active_task(batch["batch_id"])

    assert repeated["draft"]["draft_id"] == auto_draft_id
    assert get_db().assistant_drafts.count_documents({}) == 2
'''

    write(new_test, test_source)

    # Syntax-only validation. This does not require the project's runtime deps.
    for path in (service, confirmation_test, new_test):
        py_compile.compile(str(path), doraise=True)

    print("Step 1F applied successfully.")
    print("Syntax check: passed")
    print("Next task is now prepared immediately after confirm/cancel.")


if __name__ == "__main__":
    main()
