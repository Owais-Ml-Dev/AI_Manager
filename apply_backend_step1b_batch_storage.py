from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python apply_backend_step1b_batch_storage.py <backend-folder>"
    )

backend = Path(sys.argv[1]).resolve()
assistant = backend / "src/modules/assistant"

required = [
    assistant / "batch_parser.py",
    assistant / "drafts/repository.py",
    backend / "src/config/db.py",
    backend / "tests/conftest.py",
]
for path in required:
    if not path.exists():
        raise SystemExit(
            f"Required file is missing: {path}\n"
            "Apply and verify Step 1A before Step 1B."
        )


def write_new(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".before_step1b.bak")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
            print(f"Backup: {backup}")
    path.write_text(content, encoding="utf-8")
    print(f"Updated: {path}")


def replace_once(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8-sig")
    if new in text:
        print(f"Already updated: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}")
    backup = path.with_suffix(path.suffix + ".before_step1b.bak")
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
        print(f"Backup: {backup}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Updated: {path}")


write_new(
    assistant / "batches/__init__.py",
    '''"""Server-owned multi-task batch state."""\n''',
)

write_new(
    assistant / "batches/repository.py",
    '''"""MongoDB repository for assistant multi-task batches."""

from bson import ObjectId

from src.config.db import get_db


def insert_batch(document):
    db = get_db()
    result = db.assistant_task_batches.insert_one(document)
    return result.inserted_id


def find_batch(batch_id):
    db = get_db()
    return db.assistant_task_batches.find_one({"_id": ObjectId(batch_id)})
''',
)

write_new(
    assistant / "batches/service.py",
    '''"""Persistence boundary for ordered assistant task batches.

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
from src.modules.assistant.batches.repository import insert_batch


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
''',
)

# Add TTL/query indexes for the new short-lived batch collection.
db_path = backend / "src/config/db.py"
old_db = '''        db.assistant_drafts.create_index(
            [("status", ASCENDING), ("updated_at", ASCENDING)],
            name="assistant_draft_status_updated",
        )

        print(
            "MongoDB indexes verified."
        )
'''
new_db = '''        db.assistant_drafts.create_index(
            [("status", ASCENDING), ("updated_at", ASCENDING)],
            name="assistant_draft_status_updated",
        )

        # Multi-task Assistant batches are also short-lived server-owned
        # state. Only one item is active at a time; later steps attach the
        # existing assistant draft workflow to that active item.
        db.assistant_task_batches.create_index(
            [("expires_at", ASCENDING)],
            name="assistant_task_batch_ttl",
            expireAfterSeconds=0,
        )

        db.assistant_task_batches.create_index(
            [("status", ASCENDING), ("updated_at", ASCENDING)],
            name="assistant_task_batch_status_updated",
        )

        print(
            "MongoDB indexes verified."
        )
'''
replace_once(db_path, old_db, new_db)

# Ensure every DB-backed test gets a clean batch collection.
conftest = backend / "tests/conftest.py"
text = conftest.read_text(encoding="utf-8-sig")
if "db.assistant_task_batches.delete_many({})" not in text:
    old_line = "    db.assistant_drafts.delete_many({})"
    if text.count(old_line) != 2:
        raise RuntimeError(
            "Expected exactly two assistant_drafts cleanup lines in tests/conftest.py"
        )
    backup = conftest.with_suffix(conftest.suffix + ".before_step1b.bak")
    if not backup.exists():
        backup.write_bytes(conftest.read_bytes())
        print(f"Backup: {backup}")
    text = text.replace(
        old_line,
        old_line + "\n    db.assistant_task_batches.delete_many({})",
    )
    conftest.write_text(text, encoding="utf-8")
    print(f"Updated: {conftest}")
else:
    print(f"Already updated: {conftest}")

write_new(
    backend / "tests/test_assistant_task_batches.py",
    '''"""Step 1B tests: persistence and Task-1 activation only."""

import pytest

from src.config.db import get_db
from src.modules.assistant.batches.service import (
    AssistantBatchError,
    create_task_batch,
)


def _parsed_three_tasks():
    return {
        "provider": "groq",
        "model": "test-model",
        "timezone": "Asia/Kolkata",
        "fallback_used": False,
        "attempted_providers": ["groq"],
        "intents": [
            {
                "action": "create_recurring_task",
                "arguments": {"task": {"title": "Gym"}},
            },
            {
                "action": "create_repeat_until_done_task",
                "arguments": {"task": {"title": "Pay electricity"}},
            },
            {
                "action": "create_recurring_task",
                "arguments": {"task": {"title": "Call John"}},
            },
        ],
    }


def test_create_batch_persists_all_tasks_in_original_order():
    result = create_task_batch(
        _parsed_three_tasks(),
        source_message="Gym, pay electricity, call John.",
    )

    assert result["total_tasks"] == 3
    assert [
        item["intent"]["arguments"]["task"]["title"]
        for item in result["items"]
    ] == ["Gym", "Pay electricity", "Call John"]

    stored = get_db().assistant_task_batches.find_one({})
    assert stored is not None
    assert stored["total_tasks"] == 3
    assert stored["source_message"] == "Gym, pay electricity, call John."


def test_only_task_one_is_active():
    result = create_task_batch(_parsed_three_tasks())

    assert result["current_index"] == 0
    assert result["current_task_number"] == 1
    assert result["active_item"]["task_number"] == 1
    assert result["active_item"]["status"] == "active"
    assert [item["status"] for item in result["items"]] == [
        "active",
        "pending",
        "pending",
    ]


def test_step1b_does_not_create_assistant_drafts():
    create_task_batch(_parsed_three_tasks())

    db = get_db()
    assert db.assistant_task_batches.count_documents({}) == 1
    assert db.assistant_drafts.count_documents({}) == 0


def test_batch_rejects_empty_intents():
    with pytest.raises(AssistantBatchError) as error:
        create_task_batch({"intents": []})

    assert error.value.status_code == 400
''',
)

print("\nSTEP 1B APPLIED")
print("Added persistent assistant_task_batches state.")
print("Task 1 is active; Task 2..N are pending.")
print("No assistant draft is created yet and no task is executed.")
print("\nNext run from the backend folder:")
print("  python -m py_compile src/modules/assistant/batches/repository.py src/modules/assistant/batches/service.py")
print("  pytest -q tests/test_assistant_task_batches.py")
