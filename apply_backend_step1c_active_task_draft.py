from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python apply_backend_step1c_active_task_draft.py <backend-folder>"
    )

backend = Path(sys.argv[1]).resolve()
assistant = backend / "src/modules/assistant"

required = [
    assistant / "batch_parser.py",
    assistant / "batches/repository.py",
    assistant / "batches/service.py",
    assistant / "drafts/service.py",
    backend / "tests/conftest.py",
]
for path in required:
    if not path.exists():
        raise SystemExit(
            f"Required file is missing: {path}\n"
            "Apply and verify Steps 1A and 1B before Step 1C."
        )


def backup(path: Path):
    b = path.with_suffix(path.suffix + ".before_step1c.bak")
    if not b.exists():
        b.write_bytes(path.read_bytes())
        print(f"Backup: {b}")


def replace_once(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8-sig")
    if new in text:
        print(f"Already updated: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}")
    backup(path)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Updated: {path}")


def write_new(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup(path)
    path.write_text(content, encoding="utf-8")
    print(f"Updated: {path}")


# ---------------------------------------------------------------------
# 1. Preserve whether task type was explicitly stated in each batch item.
#    The create-flow must not ask for information that the user already gave.
# ---------------------------------------------------------------------
parser = assistant / "batch_parser.py"

replace_once(
    parser,
    '''                    "action": {
                        "type": "string",
                        "enum": sorted(BATCH_CREATE_ACTIONS),
                    },
                    "task": _task_fields_schema(),
                },
                "required": ["action", "task"],
''',
    '''                    "action": {
                        "type": "string",
                        "enum": sorted(BATCH_CREATE_ACTIONS),
                    },
                    "task": _task_fields_schema(),
                    "task_type_explicit": {
                        "type": "boolean",
                    },
                },
                "required": ["action", "task"],
''',
)

replace_once(
    parser,
    '''        fields = _sanitize_task_fields(item.get("task"))
        intents.append(
            {
                "action": action,
                "arguments": {"task": fields},
            }
        )
''',
    '''        fields = _sanitize_task_fields(item.get("task"))

        arguments = {"task": fields}

        # The action selected by the language model is provisional unless
        # the user explicitly stated the task type for this specific task.
        # Preserve that distinction so the deterministic create flow asks
        # only for genuinely missing information.
        if item.get("task_type_explicit") is True:
            arguments["collect"] = {
                "task_type_confirmed": True,
                "selected_task_action": action,
            }

        intents.append(
            {
                "action": action,
                "arguments": arguments,
            }
        )
''',
)

prompt = assistant / "prompts/task_batch_prompt.py"
replace_once(
    prompt,
    '''- For a create request that does not explicitly say Recurring or Repeat Until
  Done, choose the most likely create action only as a provisional parse. The
  backend will still ask the user to confirm the task type later.

For each task:
''',
    '''- For a create request that does not explicitly say Recurring or Repeat Until
  Done, choose the most likely create action only as a provisional parse. The
  backend will still ask the user to confirm the task type later.
- Set task_type_explicit=true only when that specific task explicitly states
  its type (for example Recurring/repeating/habit/routine/daily task, or
  Repeat Until Done/until done/one-time). Otherwise set it to false.

For each task:
''',
)


# ---------------------------------------------------------------------
# 2. Add a safe entry point that creates a normal assistant draft from an
#    already-parsed create intent. It reuses _evaluate_intent(), which means
#    missing fields, validation, duplicate detection and review generation all
#    remain owned by the existing single-task engine.
# ---------------------------------------------------------------------
draft_service = assistant / "drafts/service.py"
marker = '''def preview_task_draft(
    message,
'''
insert = '''def get_task_draft(draft_id):
    """Return one existing draft using the normal public response shape."""

    document = find_draft(draft_id)
    if document is None:
        raise AssistantDraftError(
            "Assistant draft was not found or expired.",
            404,
        )
    return _response(document)


def create_task_draft_from_intent(
    intent,
    timezone_name="UTC",
    provider="batch",
    model="",
    batch_id=None,
    batch_index=None,
):
    """Create a server-owned draft from an already parsed CREATE intent.

    This is the bridge used by multi-task batches. It deliberately does not
    call an AI provider again. The existing deterministic preview engine owns
    all missing-field questions, validation, duplicate checks and the final
    review command.
    """

    if not isinstance(intent, dict) or intent.get("action") not in CREATE_ACTIONS:
        raise AssistantDraftError(
            "A supported create-task intent is required.",
            400,
        )

    today = local_now(timezone_name).date()
    evaluated = _evaluate_intent(
        deepcopy(intent),
        today.isoformat(),
    )

    question = evaluated.get("question")
    question_field = (evaluated.get("missing_fields") or [None])[0]
    now = _utc_now()

    fields = {
        "status": evaluated.get("status", "collecting"),
        "intent": evaluated.get("intent", deepcopy(intent)),
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
        "last_question_field": (
            question_field
            if evaluated.get("status") == "needs_input"
            else None
        ),
        "last_question_text": (
            question
            if evaluated.get("status") == "needs_input"
            else None
        ),
        "ask_count": 1,
        "provider": provider or "batch",
        "model": model or "",
        "timezone": timezone_name,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + DRAFT_TTL,
        "executed_at": None,
        "result": None,
    }

    if batch_id is not None:
        fields["batch_id"] = str(batch_id)
    if batch_index is not None:
        fields["batch_index"] = int(batch_index)

    inserted_id = insert_draft(fields)
    fields["_id"] = inserted_id
    return _response(fields)


'''
text = draft_service.read_text(encoding="utf-8-sig")
if "def create_task_draft_from_intent(" not in text:
    if marker not in text:
        raise RuntimeError(f"Expected preview_task_draft marker not found in {draft_service}")
    backup(draft_service)
    draft_service.write_text(text.replace(marker, insert + marker, 1), encoding="utf-8")
    print(f"Updated: {draft_service}")
else:
    print(f"Already updated: {draft_service}")


# ---------------------------------------------------------------------
# 3. Atomically attach the new draft ID to the currently active batch item.
# ---------------------------------------------------------------------
batch_repo = assistant / "batches/repository.py"
replace_once(
    batch_repo,
    '''from bson import ObjectId

from src.config.db import get_db
''',
    '''from bson import ObjectId
from pymongo import ReturnDocument

from src.config.db import get_db
''',
)

repo_text = batch_repo.read_text(encoding="utf-8-sig")
repo_append = '''\n\ndef attach_draft_to_active_item(
    batch_id,
    item_index,
    draft_id,
    updated_at,
    expires_at,
):
    """Attach a draft once, only to the currently active batch item."""

    db = get_db()
    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            "items": {
                "$elemMatch": {
                    "index": item_index,
                    "status": "active",
                    "draft_id": None,
                }
            },
        },
        {
            "$set": {
                "items.$.draft_id": str(draft_id),
                "updated_at": updated_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
'''
if "def attach_draft_to_active_item(" not in repo_text:
    backup(batch_repo)
    batch_repo.write_text(repo_text.rstrip() + repo_append + "\n", encoding="utf-8")
    print(f"Updated: {batch_repo}")
else:
    print(f"Already updated: {batch_repo}")


# ---------------------------------------------------------------------
# 4. Prepare only the active item (Task 1 in Step 1C). Pending tasks remain
#    untouched. Calling this twice is idempotent and returns the same draft.
# ---------------------------------------------------------------------
batch_service = assistant / "batches/service.py"
replace_once(
    batch_service,
    '''from src.modules.assistant.batches.repository import insert_batch
''',
    '''from bson.errors import InvalidId

from src.modules.assistant.batches.repository import (
    attach_draft_to_active_item,
    find_batch,
    insert_batch,
)
from src.modules.assistant.drafts.service import (
    AssistantDraftError,
    create_task_draft_from_intent,
    get_task_draft,
)
''',
)

service_text = batch_service.read_text(encoding="utf-8-sig")
service_append = '''\n\ndef _active_item(batch):
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
'''
if "def prepare_active_task(" not in service_text:
    backup(batch_service)
    batch_service.write_text(service_text.rstrip() + service_append + "\n", encoding="utf-8")
    print(f"Updated: {batch_service}")
else:
    print(f"Already updated: {batch_service}")


# ---------------------------------------------------------------------
# 5. DB-backed Step 1C tests. The app fixture is explicitly requested so the
#    isolated test MongoDB is initialized before the global cleanup fixture.
# ---------------------------------------------------------------------
write_new(
    backend / "tests/test_assistant_batch_active_draft.py",
    '''"""Step 1C: active batch item -> existing assistant draft engine."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant.batches.service import (
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


def _intent(title="Gym", *, confirmed=False, complete=False, invalid=False):
    task = {"title": title}
    collect = {}

    if confirmed:
        collect.update(
            {
                "task_type_confirmed": True,
                "selected_task_action": "create_recurring_task",
            }
        )

    if complete or invalid:
        task.update(
            {
                "duration": {
                    "start_date": "2099-01-10" if invalid else "2099-01-01",
                    "end_date": "2099-01-01" if invalid else "2099-01-31",
                },
                "repeat": {
                    "type": "everyday",
                    "custom_dates": [],
                },
                "reminders": [
                    {
                        "start_time": "07:00",
                        "end_time": "08:00",
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

    arguments = {"task": task}
    if collect:
        arguments["collect"] = collect

    return {
        "action": "create_recurring_task",
        "arguments": arguments,
    }


def _batch_with_two(first):
    return create_task_batch(
        _parsed(
            first,
            _intent("Call John"),
        ),
        source_message="Create two tasks.",
    )


def test_prepare_task_one_asks_first_missing_field():
    batch = _batch_with_two(_intent())

    result = prepare_active_task(batch["batch_id"])

    assert result["current_task_number"] == 1
    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["task_type"]
    assert "Recurring or Repeat Until Done" in result["draft"]["question"]


def test_confirmed_task_type_skips_redundant_question():
    batch = _batch_with_two(_intent(confirmed=True))

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["duration"]


def test_present_but_invalid_information_is_not_review_ready():
    batch = _batch_with_two(
        _intent(confirmed=True, invalid=True)
    )

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] == "needs_input"
    assert result["draft"]["missing_fields"] == ["duration"]
    assert result["draft"]["validation_errors"]


def test_complete_valid_task_one_is_ready_for_review_only():
    batch = _batch_with_two(
        _intent(confirmed=True, complete=True)
    )

    result = prepare_active_task(batch["batch_id"])

    assert result["draft"]["status"] in {"ready", "duplicate_review"}
    assert result["draft"]["command"] is not None
    assert result["draft"]["command"]["requires_confirmation"] is True

    # Step 1C must not execute anything and must not activate Task 2.
    db = get_db()
    assert db.tasks.count_documents({}) == 0
    stored = db.assistant_task_batches.find_one({})
    assert stored["current_index"] == 0
    assert stored["items"][0]["status"] == "active"
    assert stored["items"][0]["draft_id"] == result["draft"]["draft_id"]
    assert stored["items"][1]["status"] == "pending"
    assert stored["items"][1]["draft_id"] is None


def test_prepare_active_task_is_idempotent():
    batch = _batch_with_two(_intent())

    first = prepare_active_task(batch["batch_id"])
    second = prepare_active_task(batch["batch_id"])

    assert first["draft"]["draft_id"] == second["draft"]["draft_id"]
    assert get_db().assistant_drafts.count_documents({}) == 1
''',
)

print("\nSTEP 1C APPLIED")
print("Task 1 now reuses the existing deterministic draft/validation engine.")
print("No task execution, batch advancement, routes, or Flutter changes were added.")
print("\nNext run from the backend folder:")
print("  python -m py_compile src/modules/assistant/batch_parser.py src/modules/assistant/batches/repository.py src/modules/assistant/batches/service.py src/modules/assistant/drafts/service.py")
print("  pytest -q tests/test_assistant_batch_active_draft.py")
