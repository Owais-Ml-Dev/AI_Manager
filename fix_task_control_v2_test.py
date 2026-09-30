from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python fix_task_control_v2_test.py <backend_dir>")

backend = Path(sys.argv[1]).resolve()
test_file = backend / "tests/test_assistant_task_control_v2.py"

if not test_file.exists():
    raise RuntimeError(f"Could not find {test_file}")

text = test_file.read_text(encoding="utf-8-sig")

old = '''    first_draft = get_db().assistant_drafts.find_one({"draft_id": first_draft_id})
    assert first_draft is not None
    assert first_draft["status"] == "cancelled"
'''

new = '''    first_draft = get_db().assistant_drafts.find_one(
        {"_id": ObjectId(first_draft_id)}
    )
    assert first_draft is not None
    assert first_draft["status"] == "cancelled"
'''

if old not in text:
    if new in text:
        print("Test is already fixed.")
        raise SystemExit(0)
    raise RuntimeError(
        "Could not find the expected failing assertion block in "
        "tests/test_assistant_task_control_v2.py"
    )

test_file.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Fixed tests/test_assistant_task_control_v2.py")
print("Draft documents are keyed by MongoDB _id, not a draft_id field.")
