"""Deterministic guided Assistant update flow.

No Gemini calls happen here.

Flow:
    update request
    -> target resolution
    -> field selection
    -> new value
    -> preview
    -> confirmation
    -> deterministic backend execution
"""

from copy import deepcopy
import re

from src.modules.assistant.command_executor import (
    TaskCommandError,
    validate_executable_command,
)
from src.modules.assistant.slot_filler import (
    extract_duration,
    extract_repeat,
    find_dates,
    parse_reminder_windows,
)


UPDATE_FIELDS = [
    "Type",
    "Title",
    "Duration",
    "Repeat",
    "Reminder window",
    "Priority",
]

PRIORITIES = [
    "Important + Urgent",
    "Important",
    "Urgent",
    "Low",
]

TASK_TYPES = [
    "Recurring",
    "Repeat Until Done",
]

REPEAT_OPTIONS = [
    "Every day",
    "Weekdays",
    "Weekends",
    "Custom dates",
]


# =========================================================
# INITIAL UPDATE COMMAND
# =========================================================

def local_update_intent(message):
    """
    Parse update commands locally without Gemini.

    Direct:
        Update gym task
        Edit swimming task

    Conversational:
        Can you update the task called swimming?
        I want to change my gym task.
        Please modify the task named Morning Workout.
    """

    raw = str(
        message or ""
    ).strip()

    if not raw:
        return None

    patterns = [
        # -----------------------------------------------
        # "update the task called Swimming Task"
        # "change my task named Gym"
        # -----------------------------------------------
        (
            r"\b"
            r"(?:update|edit|change|modify|rename|"
            r"reschedule|move)"
            r"\b"
            r"\s+"
            r"(?:my\s+|the\s+)?"
            r"(?:task|reminder|todo|to-do)"
            r"\s+"
            r"(?:called|call|named)"
            r"\s+"
            r"(.+?)"
            r"\s*$"
        ),

        # -----------------------------------------------
        # "update gym task"
        # "can you update my swimming task"
        # -----------------------------------------------
        (
            r"\b"
            r"(?:update|edit|change|modify|rename|"
            r"reschedule|move)"
            r"\b"
            r"\s+"
            r"(?:my\s+|the\s+)?"
            r"(.+?)"
            r"\s*$"
        ),
    ]

    target = None

    for pattern in patterns:
        match = re.search(
            pattern,
            raw,
            re.IGNORECASE,
        )

        if match is not None:
            target = (
                match.group(1)
                .strip(
                    " .,'\"?!"
                )
            )

            break

    if not target:
        return None

    # Remove:
    #
    # task called X
    # task named X
    target = re.sub(
        r"^(?:task|reminder|todo|to-do)"
        r"\s+(?:called|call|named)\s+",
        "",
        target,
        flags=re.IGNORECASE,
    )

    # Remove trailing:
    #
    # swimming task
    # gym reminder
    target = re.sub(
        r"\s+(?:task|reminder|todo|to-do)$",
        "",
        target,
        flags=re.IGNORECASE,
    )

    target = target.strip(
        " .,'\"?!"
    )

    if (
        not target
        or target.lower()
        in {
            "task",
            "the task",
            "my task",
            "reminder",
            "it",
            "this",
            "that",
        }
    ):
        return None

    return {
        "action":
            "update_task",

        "arguments": {
            "target_text":
                target,
        },
    }

def attach_update_target(
    intent,
    candidate,
):
    value = (
        deepcopy(intent)
        if isinstance(
            intent,
            dict,
        )
        else {}
    )

    arguments = deepcopy(
        value.get(
            "arguments",
        )
        or {}
    )

    arguments[
        "selected_target"
    ] = deepcopy(
        candidate
    )

    arguments.setdefault(
        "changes",
        {},
    )

    arguments.setdefault(
        "update_collect",
        {},
    )

    value[
        "action"
    ] = "update_task"

    value[
        "arguments"
    ] = arguments

    return value


def _target(
    intent,
):
    arguments = (
        intent.get(
            "arguments",
        )
        if isinstance(
            intent,
            dict,
        )
        else {}
    ) or {}

    value = arguments.get(
        "selected_target"
    )

    return (
        deepcopy(value)
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def _collect(
    intent,
):
    arguments = (
        intent.get(
            "arguments",
        )
        if isinstance(
            intent,
            dict,
        )
        else {}
    ) or {}

    return dict(
        arguments.get(
            "update_collect",
        )
        or {}
    )


def _changes(
    intent,
):
    arguments = (
        intent.get(
            "arguments",
        )
        if isinstance(
            intent,
            dict,
        )
        else {}
    ) or {}

    value = arguments.get(
        "changes",
    )

    return (
        deepcopy(value)
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def _with_state(
    intent,
    collect=None,
    changes=None,
):
    value = deepcopy(
        intent
    )

    arguments = deepcopy(
        value.get(
            "arguments",
        )
        or {}
    )

    if collect is not None:
        arguments[
            "update_collect"
        ] = deepcopy(
            collect
        )

    if changes is not None:
        arguments[
            "changes"
        ] = deepcopy(
            changes
        )

    value[
        "arguments"
    ] = arguments

    return value


# =========================================================
# FIELD PARSERS
# =========================================================

def _selected_field(
    reply,
):
    value = re.sub(
        r"\s+",
        " ",
        str(
            reply or ""
        ).strip().lower(),
    )

    if value in {
        "type",
        "task type",
    }:
        return "type"

    if value in {
        "title",
        "name",
        "task title",
        "task name",
    }:
        return "title"

    if value in {
        "duration",
        "dates",
        "date",
        "start and end date",
    }:
        return "duration"

    if value in {
        "repeat",
        "schedule",
        "recurrence",
        "repeat schedule",
    }:
        return "repeat"

    if value in {
        "reminder",
        "reminders",
        "reminder window",
        "reminder windows",
        "notification",
        "notifications",
    }:
        return "reminders"

    if value in {
        "priority",
        "importance",
    }:
        return "priority"

    return None


def _priority(
    reply,
):
    value = re.sub(
        r"\s+",
        " ",
        str(
            reply or ""
        ).strip().lower(),
    )

    if value in {
        "important + urgent",
        "important urgent",
    }:
        return (
            "important_urgent"
        )

    if value in {
        "important",
        "important not urgent",
        "important + not urgent",
    }:
        return (
            "important_not_urgent"
        )

    if value in {
        "urgent",
        "not important urgent",
        "not important + urgent",
    }:
        return (
            "not_important_urgent"
        )

    if value in {
        "low",
        "not important not urgent",
        "not important + not urgent",
    }:
        return (
            "not_important_not_urgent"
        )

    return None


def _task_type(
    reply,
):
    value = re.sub(
        r"\s+",
        " ",
        str(
            reply or ""
        ).strip().lower(),
    )

    if value in {
        "recurring",
        "daily",
        "habit",
        "routine",
    }:
        return "recurring"

    if value in {
        "repeat until done",
        "until done",
        "one time",
        "one-time",
    }:
        return (
            "repeat_until_done"
        )

    return None


def _number(
    reply,
    minimum=1,
    maximum=20,
):
    match = re.search(
        r"\b(\d{1,2})\b",
        str(
            reply or ""
        ),
    )

    if not match:
        return None

    value = int(
        match.group(1)
    )

    if not (
        minimum
        <= value
        <= maximum
    ):
        return None

    return value


# =========================================================
# QUESTIONS
# =========================================================

def _reminder_label(
    index,
    reminder,
):
    return (
        f"{index + 1}. "
        f"{reminder.get('start_time', '?')} - "
        f"{reminder.get('end_time', '?')} ? "
        f"{reminder.get('count', 1)} reminder(s)"
    )


def next_update_step(
    intent,
):
    target = _target(
        intent
    )

    if not target:
        return None

    collect = _collect(
        intent
    )

    changes = _changes(
        intent
    )

    field = collect.get(
        "field"
    )

    # -----------------------------------------------------
    # CHOOSE FIELD
    # -----------------------------------------------------

    if not field:
        return {
            "field":
                "update_field",

            "question":
                "What would you like to update?",

            "suggestions":
                UPDATE_FIELDS,
        }

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    if field == "type":

        if not collect.get(
            "target_task_type"
        ):
            current = (
                "Recurring"
                if target.get(
                    "task_type"
                )
                == "recurring"
                else "Repeat Until Done"
            )

            return {
                "field":
                    "update.type",

                "question":
                    (
                        f"This task is currently {current}. "
                        "What type should it become?"
                    ),

                "suggestions":
                    TASK_TYPES,
            }

        return None

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    if field == "title":

        if "title" not in changes:
            return {
                "field":
                    "update.title",

                "question":
                    "What should the new task title be?",

                "suggestions":
                    [],
            }

        return None

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    if field == "duration":

        if "duration" not in changes:
            return {
                "field":
                    "update.duration",

                "question":
                    (
                        "What should the new start and end dates be? "
                        "For example: 1 Oct to 31 Oct."
                    ),

                "suggestions":
                    [],
            }

        return None

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    if field == "repeat":

        if "repeat" not in changes:
            return {
                "field":
                    "update.repeat",

                "question":
                    "How should the task repeat?",

                "suggestions":
                    REPEAT_OPTIONS,
            }

        return None

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    if field == "priority":

        if "priority" not in changes:
            return {
                "field":
                    "update.priority",

                "question":
                    "What priority should the task have?",

                "suggestions":
                    PRIORITIES,
            }

        return None

    # -----------------------------------------------------
    # REMINDER WINDOW
    # -----------------------------------------------------

    if field == "reminders":

        raw = target.get(
            "reminders"
        )

        reminders = (
            deepcopy(raw)
            if isinstance(
                raw,
                list,
            )
            else []
        )

        reminder_index = (
            collect.get(
                "reminder_index"
            )
        )

        if reminder_index is None:

            if len(
                reminders
            ) > 1:
                return {
                    "field":
                        "update.reminder_index",

                    "question":
                        (
                            "Which reminder window "
                            "do you want to update?"
                        ),

                    "suggestions": [
                        _reminder_label(
                            index,
                            reminder,
                        )
                        for (
                            index,
                            reminder,
                        )
                        in enumerate(
                            reminders
                        )
                    ],
                }

        if not isinstance(
            collect.get(
                "pending_reminder_window"
            ),
            dict,
        ):
            return {
                "field":
                    "update.reminder_window",

                "question":
                    (
                        "What should the new reminder "
                        "window be? For example: "
                        "3:40 PM to 3:50 PM."
                    ),

                "suggestions":
                    [],
            }

        if (
            collect.get(
                "pending_reminder_count"
            )
            is None
        ):
            window = collect[
                "pending_reminder_window"
            ]

            return {
                "field":
                    "update.reminder_count",

                "question":
                    (
                        "How many reminders should I send "
                        "in this window "
                        f"({window.get('start_time')} - "
                        f"{window.get('end_time')})?"
                    ),

                "suggestions": [
                    "1",
                    "2",
                    "3",
                ],
            }

        return None

    return None


# =========================================================
# ANSWERS
# =========================================================

def apply_update_answer(
    field,
    intent,
    reply,
    today,
):
    value = deepcopy(
        intent
    )

    target = _target(
        value
    )

    collect = _collect(
        value
    )

    changes = _changes(
        value
    )

    # -----------------------------------------------------
    # FIELD
    # -----------------------------------------------------

    if field == "update_field":

        selected = _selected_field(
            reply
        )

        if not selected:
            return value, False

        collect = {
            "field":
                selected,
        }

        changes = {}

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    if field == "update.title":

        title = str(
            reply or ""
        ).strip()

        if not title:
            return value, False

        changes[
            "title"
        ] = title

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    if field == "update.duration":

        duration = (
            extract_duration(
                reply,
                today,
                lenient=True,
            )
        )

        if (
            not isinstance(
                duration,
                dict,
            )
            or not duration.get(
                "start_date"
            )
            or not duration.get(
                "end_date"
            )
        ):
            return value, False

        changes[
            "duration"
        ] = duration

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    if field == "update.repeat":

        repeat = extract_repeat(
            reply
        )

        if not isinstance(
            repeat,
            dict,
        ):
            return value, False

        if (
            repeat.get(
                "type"
            )
            == "custom_dates"
        ):
            dates = find_dates(
                reply,
                today,
            )

            if not dates:
                return value, False

            repeat[
                "custom_dates"
            ] = [
                item.isoformat()
                for item in dates
            ]

        changes[
            "repeat"
        ] = repeat

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    if field == "update.priority":

        priority = _priority(
            reply
        )

        if not priority:
            return value, False

        changes[
            "priority"
        ] = priority

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    if field == "update.type":

        target_type = (
            _task_type(
                reply
            )
        )

        if (
            not target_type
            or target_type
            == target.get(
                "task_type"
            )
        ):
            return value, False

        collect[
            "target_task_type"
        ] = target_type

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # REMINDER INDEX
    # -----------------------------------------------------

    if (
        field
        == "update.reminder_index"
    ):

        number = _number(
            reply
        )

        reminders = (
            target.get(
                "reminders"
            )
            if isinstance(
                target.get(
                    "reminders"
                ),
                list,
            )
            else []
        )

        if (
            number is None
            or number
            > len(
                reminders
            )
        ):
            return value, False

        collect[
            "reminder_index"
        ] = (
            number - 1
        )

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # REMINDER WINDOW
    # -----------------------------------------------------

    if (
        field
        == "update.reminder_window"
    ):

        windows, ambiguous = (
            parse_reminder_windows(
                reply,
                lenient=True,
            )
        )

        if (
            ambiguous
            or not windows
            or len(
                windows
            )
            != 1
        ):
            return value, False

        collect[
            "pending_reminder_window"
        ] = {
            "start_time":
                windows[0][
                    "start_time"
                ],

            "end_time":
                windows[0][
                    "end_time"
                ],
        }

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    # -----------------------------------------------------
    # REMINDER COUNT
    # -----------------------------------------------------

    if (
        field
        == "update.reminder_count"
    ):

        count = _number(
            reply,
            1,
            20,
        )

        if count is None:
            return value, False

        collect[
            "pending_reminder_count"
        ] = count

        raw = target.get(
            "reminders"
        )

        reminders = (
            deepcopy(raw)
            if isinstance(
                raw,
                list,
            )
            else []
        )

        index = int(
            collect.get(
                "reminder_index"
            )
            or 0
        )

        new_reminder = deepcopy(
            collect.get(
                "pending_reminder_window"
            )
            or {}
        )

        new_reminder[
            "count"
        ] = count

        if reminders:

            if index >= len(
                reminders
            ):
                index = (
                    len(
                        reminders
                    )
                    - 1
                )

            reminders[
                index
            ] = new_reminder

        else:
            reminders = [
                new_reminder
            ]

        changes[
            "reminders"
        ] = reminders

        return (
            _with_state(
                value,
                collect,
                changes,
            ),
            True,
        )

    return value, False


# =========================================================
# PREVIEW
# =========================================================

def _priority_name(
    value,
):
    return {
        "important_urgent":
            "Important + Urgent",

        "important_not_urgent":
            "Important",

        "not_important_urgent":
            "Urgent",

        "not_important_not_urgent":
            "Low",
    }.get(
        value,
        str(
            value or ""
        ),
    )


def _repeat_name(
    value,
):
    return {
        "everyday":
            "Every day",

        "weekdays":
            "Weekdays",

        "weekends":
            "Weekends",

        "custom_dates":
            "Custom dates",
    }.get(
        value,
        str(
            value or ""
        ),
    )


def _summary(
    intent,
):
    target = _target(
        intent
    )

    collect = _collect(
        intent
    )

    changes = _changes(
        intent
    )

    title = (
        target.get(
            "title"
        )
        or "task"
    )

    field = collect.get(
        "field"
    )

    if field == "type":

        before = (
            "Recurring"
            if target.get(
                "task_type"
            )
            == "recurring"
            else "Repeat Until Done"
        )

        after = (
            "Recurring"
            if collect.get(
                "target_task_type"
            )
            == "recurring"
            else "Repeat Until Done"
        )

        return (
            f"Change {title} type: "
            f"{before} ? {after}. "
            "This creates the new task type and "
            "removes the old task. Existing recurring "
            "occurrence history for the old task will "
            "also be removed."
        )

    if field == "title":

        return (
            f"Update {title} title: "
            f"{target.get('title')} ? "
            f"{changes.get('title')}."
        )

    if field == "duration":

        before = (
            target.get(
                "duration"
            )
            or {}
        )

        after = (
            changes.get(
                "duration"
            )
            or {}
        )

        return (
            f"Update {title} duration: "
            f"{before.get('start_date')} to "
            f"{before.get('end_date')} ? "
            f"{after.get('start_date')} to "
            f"{after.get('end_date')}."
        )

    if field == "repeat":

        before = (
            target.get(
                "repeat"
            )
            or {}
        )

        after = (
            changes.get(
                "repeat"
            )
            or {}
        )

        return (
            f"Update {title} repeat: "
            f"{_repeat_name(before.get('type'))} ? "
            f"{_repeat_name(after.get('type'))}."
        )

    if field == "priority":

        return (
            f"Update {title} priority: "
            f"{_priority_name(target.get('priority'))} ? "
            f"{_priority_name(changes.get('priority'))}."
        )

    if field == "reminders":

        index = int(
            collect.get(
                "reminder_index"
            )
            or 0
        )

        before_list = (
            target.get(
                "reminders"
            )
            if isinstance(
                target.get(
                    "reminders"
                ),
                list,
            )
            else []
        )

        after_list = (
            changes.get(
                "reminders"
            )
            if isinstance(
                changes.get(
                    "reminders"
                ),
                list,
            )
            else []
        )

        before = (
            before_list[
                index
            ]
            if index
            < len(
                before_list
            )
            else {}
        )

        after = (
            after_list[
                index
            ]
            if index
            < len(
                after_list
            )
            else {}
        )

        return (
            f"Update {title} reminder window "
            f"{index + 1}: "
            f"{before.get('start_time')} - "
            f"{before.get('end_time')} "
            f"({before.get('count', 1)} reminder(s)) ? "
            f"{after.get('start_time')} - "
            f"{after.get('end_time')} "
            f"({after.get('count', 1)} reminder(s))."
        )

    return (
        f"Update {title}."
    )


def build_update_preview(
    intent,
):
    target = _target(
        intent
    )

    if not target:
        return None

    step = next_update_step(
        intent
    )

    if step:

        return {
            "status":
                "needs_input",

            "missing_fields": [
                step[
                    "field"
                ]
            ],

            "question":
                step[
                    "question"
                ],

            "suggestions":
                step.get(
                    "suggestions",
                    [],
                ),

            "intent":
                intent,

            "command":
                None,
        }

    collect = _collect(
        intent
    )

    changes = _changes(
        intent
    )

    task_id = target.get(
        "id"
    )

    task_type = target.get(
        "task_type"
    )

    if (
        collect.get(
            "field"
        )
        == "type"
    ):
        command = {
            "action":
                "convert_task_type",

            "arguments": {
                "task_id":
                    task_id,

                "source_task_type":
                    task_type,

                "target_task_type":
                    collect.get(
                        "target_task_type"
                    ),
            },

            "summary":
                _summary(
                    intent
                ),

            "requires_confirmation":
                True,
        }

    else:

        concrete = (
            "update_repeat_until_done_task"
            if task_type
            == "repeat_until_done"
            else "update_recurring_task"
        )

        command = {
            "action":
                concrete,

            "arguments": {
                "task_id":
                    task_id,

                "changes":
                    changes,
            },

            "summary":
                _summary(
                    intent
                ),

            "requires_confirmation":
                True,
        }

    try:
        validate_executable_command(
            command
        )

    except TaskCommandError as error:

        return {
            "status":
                "needs_input",

            "missing_fields":
                [],

            "question":
                error.message,

            "validation_errors":
                error.errors
                or {},

            "suggestions":
                [],

            "intent":
                intent,

            "command":
                None,
        }

    return {
        "status":
            "ready",

        "missing_fields":
            [],

        "question":
            None,

        "suggestions":
            [],

        "intent":
            intent,

        "command":
            command,
    }


UPDATE_RETRY_QUESTIONS = {
    "update_field":
        (
            "Choose Type, Title, Duration, Repeat, "
            "Reminder window, or Priority."
        ),

    "update.type":
        (
            "Choose Recurring or Repeat Until Done."
        ),

    "update.title":
        (
            "Please enter the new task title."
        ),

    "update.duration":
        (
            "Give both start and end dates. "
            "For example: 1 Oct to 31 Oct."
        ),

    "update.repeat":
        (
            "Choose Every day, Weekdays, "
            "Weekends, or Custom dates."
        ),

    "update.priority":
        (
            "Choose Important + Urgent, "
            "Important, Urgent, or Low."
        ),

    "update.reminder_index":
        (
            "Choose one of the reminder "
            "window numbers shown above."
        ),

    "update.reminder_window":
        (
            "Give one start and end time. "
            "For example: 3:40 PM to 3:50 PM."
        ),

    "update.reminder_count":
        (
            "Enter a reminder count from 1 to 20."
        ),
}
