from pathlib import Path

ROOT = Path(".").resolve()


def read(path):
    return path.read_text(
        encoding="utf-8-sig"
    )


def write(path, text):
    path.write_text(
        text,
        encoding="utf-8"
    )


# =========================================================
# 1. ADD LOCAL DELETE PARSER
# =========================================================

path = (
    ROOT
    / "src"
    / "modules"
    / "assistant"
    / "create_flow.py"
)

text = read(path)

if "def _local_delete_target(" not in text:

    marker = "\ndef local_intent(message, today):\n"

    if marker not in text:
        raise RuntimeError(
            "local_intent() not found."
        )

    helper = r'''

def _local_delete_target(message):
    """
    Extract the task name from an explicit delete command
    without calling Gemini.

    Examples:

        Delete swim task
            -> swim

        Remove my Swimming reminder
            -> Swimming

        Delete task called Morning Exercise
            -> Morning Exercise
    """

    raw = str(
        message or ""
    ).strip()

    match = re.match(
        r"^(?:please\s+)?"
        r"(?:delete|remove)\s+"
        r"(?:my\s+|the\s+)?"
        r"(.+?)\s*$",
        raw,
        re.IGNORECASE,
    )

    if not match:
        return None

    target = (
        match.group(1)
        .strip(
            " .,'\"“”"
        )
    )

    # Example:
    # "task called Swimming"
    # -> "Swimming"
    target = re.sub(
        r"^(?:task|reminder|todo|to-do)"
        r"\s+(?:called|named)\s+",
        "",
        target,
        flags=re.IGNORECASE,
    )

    # Example:
    # "swim task"
    # -> "swim"
    target = re.sub(
        r"\s+(?:task|reminder|todo|to-do)$",
        "",
        target,
        flags=re.IGNORECASE,
    ).strip(
        " .,'\"“”"
    )

    if (
        not target
        or target.lower()
        in {
            "task",
            "reminder",
            "it",
            "this",
            "that",
        }
    ):
        return None

    return target
'''

    text = text.replace(
        marker,
        helper + marker,
        1,
    )


# =========================================================
# 2. MAKE local_intent() UNDERSTAND DELETE
# =========================================================

needle = '''    text = str(message or "").strip().lower()

'''

if needle not in text:
    raise RuntimeError(
        "Could not find local_intent text normalization."
    )

replacement = '''    text = str(message or "").strip().lower()

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------
    #
    # Explicit delete commands do not require Gemini.
    #
    # "Delete swim task"
    #       ↓
    # action = delete_task
    # target_text = swim
    #
    delete_target = _local_delete_target(
        message
    )

    if delete_target:
        return {
            "action":
                "delete_task",

            "arguments": {
                "target_text":
                    delete_target,
            },
        }

'''

text = text.replace(
    needle,
    replacement,
    1,
)

write(
    path,
    text,
)


# =========================================================
# 3. BYPASS GEMINI FOR CLEAR DELETE COMMANDS
# =========================================================

path = (
    ROOT
    / "src"
    / "modules"
    / "assistant"
    / "drafts"
    / "service.py"
)

text = read(path)

old = '''    # ---- 2. Gemini --------------------------------------------------------
    if intent is None:
'''

new = '''    # ---- 2. Explicit DELETE: deterministic -------------------------------
    #
    # A command such as:
    #
    #     Delete swim task
    #
    # is unambiguous enough that Gemini adds no value.
    #
    # Parse it locally and let the existing MongoDB matcher
    # resolve the actual task.
    #
    # This also means Gemini outages cannot block deletion.
    #
    if (
        intent is None
        and not answering
    ):
        deterministic = local_intent(
            message,
            today,
        )

        if (
            deterministic
            and deterministic.get(
                "action"
            )
            == "delete_task"
        ):
            intent = deterministic

            provider = "local"

            model = (
                "deterministic parser"
            )

    # ---- 3. Gemini --------------------------------------------------------
    if intent is None:
'''

if old not in text:

    # Allow re-running safely.
    if (
        "Explicit DELETE: deterministic"
        not in text
    ):
        raise RuntimeError(
            "Gemini section in drafts/service.py "
            "was not found."
        )

else:
    text = text.replace(
        old,
        new,
        1,
    )

write(
    path,
    text,
)


# =========================================================
# 4. ADD UNIT TEST FOR LOCAL DELETE PARSING
# =========================================================

path = (
    ROOT
    / "tests"
    / "test_assistant_followups.py"
)

text = read(path)

test_name = (
    "test_local_delete_intent_does_not_need_gemini"
)

if test_name not in text:

    text += r'''


def test_local_delete_intent_does_not_need_gemini():
    intent = local_intent(
        "Delete swim task",
        TODAY,
    )

    assert intent == {
        "action": "delete_task",
        "arguments": {
            "target_text": "swim",
        },
    }
'''

write(
    path,
    text,
)


# =========================================================
# 5. ADD END-TO-END PREVIEW TEST:
#    GEMINI MUST NOT BE CALLED
# =========================================================

path = (
    ROOT
    / "tests"
    / "test_assistant_task_commands.py"
)

text = read(path)

test_name = (
    "test_delete_preview_bypasses_gemini"
)

if test_name not in text:

    text += r'''


def test_delete_preview_bypasses_gemini(
    client,
    monkeypatch,
):
    """
    A clear delete command must work even when Gemini is
    unavailable because delete intent parsing is deterministic.
    """

    from datetime import datetime, timezone

    db = get_db()

    task_id = db.tasks.insert_one(
        {
            "task_type":
                "repeat_until_done",

            "title":
                "Swim",

            "description":
                "Swimming task",

            "priority":
                "not_important_not_urgent",

            "duration": {
                "start_date":
                    "2026-09-24",

                "end_date":
                    "2026-10-24",
            },

            "repeat": {
                "type":
                    "everyday",

                "custom_dates":
                    [],
            },

            "reminders":
                [],

            "status":
                "pending",

            "reminders_cancelled":
                False,

            "created_at":
                datetime.now(
                    timezone.utc
                ),

            "updated_at":
                datetime.now(
                    timezone.utc
                ),
        }
    ).inserted_id

    def gemini_must_not_run(
        **kwargs,
    ):
        raise AssertionError(
            "Gemini must not be called "
            "for an explicit delete command."
        )

    monkeypatch.setattr(
        "src.modules.assistant.drafts."
        "service.parse_task_message",
        gemini_must_not_run,
    )

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message":
                "Delete swim task",

            "timezone":
                "+05:30",
        },
    )

    assert (
        response.status_code
        == 200
    )

    data = (
        response
        .get_json()["data"]
    )

    assert (
        data["status"]
        == "ready"
    )

    assert (
        data["command"]["action"]
        == "delete_repeat_until_done_task"
    )

    assert (
        data["command"]
        ["arguments"]
        ["task_id"]
        == str(task_id)
    )

    assert (
        data["command"]
        ["requires_confirmation"]
        is True
    )
'''

write(
    path,
    text,
)


print()
print(
    "SUCCESS: Delete commands now bypass Gemini."
)
print(
    'Example: "Delete swim task"'
)
print(
    "-> local parser"
)
print(
    "-> MongoDB task matcher"
)
print(
    "-> confirmation"
)
print(
    "-> backend delete"
)
