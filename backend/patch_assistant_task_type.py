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


def replace_once(path, old, new):
    text = read(path)

    if old not in text:
        raise RuntimeError(
            f"Expected block not found in:\n{path}\n\n"
            f"Beginning of expected block:\n{old[:250]}"
        )

    text = text.replace(
        old,
        new,
        1
    )

    write(
        path,
        text
    )


# =========================================================
# 1. CREATE FLOW
# =========================================================

path = (
    ROOT
    / "src"
    / "modules"
    / "assistant"
    / "create_flow.py"
)


# ---------------------------------------------------------
# Add task-type detection helpers
# ---------------------------------------------------------

replace_once(
    path,
    '''CREATE_ACTIONS = {"create_repeat_until_done_task", "create_recurring_task"}
MAX_WINDOWS = 5
''',
    '''CREATE_ACTIONS = {"create_repeat_until_done_task", "create_recurring_task"}
MAX_WINDOWS = 5


def explicit_task_action(text):
    """
    Return a create action only when the user explicitly
    specifies the task type.

    Example:
        "Add swimming task"
            -> None

        "Add recurring swimming task"
            -> create_recurring_task

        "Add repeat until done swimming task"
            -> create_repeat_until_done_task
    """

    value = str(
        text or ""
    ).strip().lower()

    if re.search(
        r"\\b("
        r"repeat[- ]?until[- ]?done"
        r"|until done"
        r"|one[- ]?time"
        r")\\b",
        value,
    ):
        return (
            "create_repeat_until_done_task"
        )

    if re.search(
        r"\\b("
        r"recurring"
        r"|repeating"
        r"|habit"
        r"|routine"
        r")\\b"
        r"|\\bdaily\\s+task\\b",
        value,
    ):
        return (
            "create_recurring_task"
        )

    return None


def selected_create_action(
    action,
    collect,
):
    """
    Return the task type explicitly selected by the user.

    Gemini's original classification is only provisional
    until the user confirms the type.
    """

    selected = (
        collect or {}
    ).get(
        "selected_task_action"
    )

    if selected in CREATE_ACTIONS:
        return selected

    return action
'''
)


# ---------------------------------------------------------
# Ask task type BEFORE duration
# ---------------------------------------------------------

replace_once(
    path,
    '''    if not str(task.get("title") or "").strip():
        return {
            "field": "title",
            "question": "What should I call this task?",
            "suggestions": [],
        }

    duration = task.get("duration") if isinstance(task.get("duration"), dict) else {}
''',
    '''    if not str(task.get("title") or "").strip():
        return {
            "field": "title",
            "question": "What should I call this task?",
            "suggestions": [],
        }

    # -----------------------------------------------------
    # TASK TYPE
    # -----------------------------------------------------
    #
    # Gemini may provisionally classify a create request,
    # but we do not silently decide between:
    #
    #   Recurring
    #   Repeat Until Done
    #
    # unless the user explicitly stated the type.
    #
    if not collect.get(
        "task_type_confirmed"
    ):
        return {
            "field": "task_type",
            "question": (
                "What type of task is this: "
                "Recurring or Repeat Until Done?"
            ),
            "suggestions": [
                "Recurring",
                "Repeat Until Done",
            ],
        }

    duration = task.get("duration") if isinstance(task.get("duration"), dict) else {}
'''
)


# ---------------------------------------------------------
# Retry question
# ---------------------------------------------------------

replace_once(
    path,
    '''RETRY_QUESTIONS = {
    "title": "I still need a name for this task. Just type the name, for example: Buy groceries.",
''',
    '''RETRY_QUESTIONS = {
    "title": "I still need a name for this task. Just type the name, for example: Buy groceries.",

    "task_type": (
        "Please choose the task type: "
        "Recurring or Repeat Until Done."
    ),
'''
)


# ---------------------------------------------------------
# Read task-type answer
# ---------------------------------------------------------

replace_once(
    path,
    '''    if field == "title":
        title = extract_title(reply)
        if title:
            task["title"] = title
            understood = True

    elif field in ("duration", "duration.start_date", "duration.end_date"):
''',
    '''    if field == "title":
        title = extract_title(
            reply
        )

        if title:
            task["title"] = title
            understood = True

    elif field == "task_type":

        selected = (
            explicit_task_action(
                reply
            )
        )

        value = str(
            reply or ""
        ).strip().lower()

        # Because we explicitly asked:
        #
        # "Recurring or Repeat Until Done?"
        #
        # short answers can safely be interpreted here.

        if selected is None and value in {
            "recurring",
            "daily",
            "repeating",
            "habit",
            "routine",
        }:
            selected = (
                "create_recurring_task"
            )

        elif selected is None and value in {
            "repeat until done",
            "until done",
            "one time",
            "one-time",
        }:
            selected = (
                "create_repeat_until_done_task"
            )

        if selected in CREATE_ACTIONS:

            collect[
                "selected_task_action"
            ] = selected

            collect[
                "task_type_confirmed"
            ] = True

            understood = True

    elif field in (
        "duration",
        "duration.start_date",
        "duration.end_date",
    ):
'''
)


# ---------------------------------------------------------
# First-message explicit task-type detection
# ---------------------------------------------------------

replace_once(
    path,
    '''    task = deepcopy(task) if isinstance(task, dict) else {}
    collect = dict(collect or {})

    windows, ambiguous = parse_reminder_windows(message)
''',
    '''    task = (
        deepcopy(task)
        if isinstance(
            task,
            dict
        )
        else {}
    )

    collect = dict(
        collect or {}
    )

    # If the user explicitly says the task type in the
    # first message, do not ask again.
    #
    # Examples:
    #
    # "Create recurring swimming task"
    #
    # "Create repeat until done swimming task"
    #
    explicit_action = (
        explicit_task_action(
            message
        )
    )

    if explicit_action in CREATE_ACTIONS:

        collect[
            "selected_task_action"
        ] = explicit_action

        collect[
            "task_type_confirmed"
        ] = True

    windows, ambiguous = (
        parse_reminder_windows(
            message
        )
    )
'''
)


# =========================================================
# 2. DRAFT SERVICE
# =========================================================

path = (
    ROOT
    / "src"
    / "modules"
    / "assistant"
    / "drafts"
    / "service.py"
)


# ---------------------------------------------------------
# Import selected_create_action
# ---------------------------------------------------------

replace_once(
    path,
    '''from src.modules.assistant.create_flow import (
    RETRY_QUESTIONS,
    apply_answer,
    local_intent,
    prefill_from_message,
)
''',
    '''from src.modules.assistant.create_flow import (
    RETRY_QUESTIONS,
    apply_answer,
    local_intent,
    prefill_from_message,
    selected_create_action,
)
'''
)


# ---------------------------------------------------------
# Duration is valid for BOTH task types now.
#
# Remove old code that deleted duration when the draft
# switched to Repeat Until Done.
# ---------------------------------------------------------

text = read(
    path
)

text = text.replace(
    '''        if incoming_action != "create_recurring_task":
            task.pop("duration", None)
''',
    '',
    1,
)

write(
    path,
    text
)


# ---------------------------------------------------------
# When user answers task type, switch the action
# ---------------------------------------------------------

replace_once(
    path,
    '''        if understood:
            local_answer = _with_task(current_intent, task, collect)
            if len(message.split()) <= SHORT_REPLY_WORDS:
                intent = local_answer
''',
    '''        if understood:

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
'''
)


# ---------------------------------------------------------
# Offline/local parser path
# ---------------------------------------------------------

replace_once(
    path,
    '''                    task, collect = prefill_from_message(
                        intent["action"], _task_of(intent), {}, message, today
                    )
                    intent = _with_task(intent, task, collect)
''',
    '''                    task, collect = (
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
'''
)


# ---------------------------------------------------------
# Gemini path
# ---------------------------------------------------------

replace_once(
    path,
    '''                intent = _with_task(intent, task, collect)

    evaluated = _evaluate_intent(intent, today.isoformat())
''',
    '''                resolved_action = (
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
'''
)


# =========================================================
# 3. GEMINI PROMPT
# =========================================================

path = (
    ROOT
    / "src"
    / "modules"
    / "assistant"
    / "prompts"
    / "task_command_prompt.py"
)

replace_once(
    path,
    '''- unknown: not about tasks.
If the message answers QUESTION THE USER IS ANSWERING, or only adds details,
use the action from CURRENT DRAFT.
''',
    '''- unknown: not about tasks.

For a create request that does NOT explicitly say
Recurring or Repeat Until Done, choose the most likely
create action only as a provisional parse.

The backend will ask the user to explicitly choose the
task type before creating anything.

If the message answers QUESTION THE USER IS ANSWERING,
or only adds details, use the action from CURRENT DRAFT.
'''
)


# =========================================================
# 4. ADD AUTOMATED TESTS
# =========================================================

test_path = (
    ROOT
    / "tests"
    / "test_assistant_task_type_selection.py"
)

test_path.write_text(
r'''
from datetime import date

from src.modules.assistant.create_flow import (
    apply_answer,
    next_step,
    prefill_from_message,
    selected_create_action,
)


def test_plain_create_asks_task_type_first():

    task, collect = (
        prefill_from_message(
            "create_repeat_until_done_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Add swimming task",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    step = next_step(
        "create_repeat_until_done_task",
        task,
        collect,
    )

    assert (
        step["field"]
        == "task_type"
    )

    assert (
        step["suggestions"]
        == [
            "Recurring",
            "Repeat Until Done",
        ]
    )


def test_explicit_recurring_skips_type_question():

    task, collect = (
        prefill_from_message(
            "create_recurring_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Add recurring swimming task",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    step = next_step(
        "create_recurring_task",
        task,
        collect,
    )

    assert (
        collect[
            "task_type_confirmed"
        ]
        is True
    )

    assert (
        step["field"]
        == "duration"
    )


def test_can_switch_from_provisional_rud_to_recurring():

    task, collect, understood = (
        apply_answer(
            "task_type",
            "create_repeat_until_done_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Recurring",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    assert understood is True

    assert (
        selected_create_action(
            "create_repeat_until_done_task",
            collect,
        )
        == "create_recurring_task"
    )

    assert (
        task["title"]
        == "Swimming"
    )


def test_can_switch_from_provisional_recurring_to_rud():

    task, collect, understood = (
        apply_answer(
            "task_type",
            "create_recurring_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Repeat Until Done",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    assert understood is True

    assert (
        selected_create_action(
            "create_recurring_task",
            collect,
        )
        == "create_repeat_until_done_task"
    )

    assert (
        task["title"]
        == "Swimming"
    )
'''.lstrip(),
    encoding="utf-8",
)


print()
print(
    "SUCCESS: Assistant task-type selection flow updated."
)
print()
print(
    "Plain task requests will now ask:"
)
print(
    "Recurring or Repeat Until Done?"
)
