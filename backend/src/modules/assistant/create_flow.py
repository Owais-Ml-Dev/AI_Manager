"""Step-by-step collection of a new task's details.

The assistant asks for exactly one thing at a time, in this order:

Recurring task
    1. Dates           start date and end date
    2. Repeat          every day / weekdays / weekends / custom dates
    3. Window count    how many reminder windows
    4. Each window     start time and end time, one window at a time

Repeat Until Done task
    1. Repeat          every day / weekdays / weekends / custom dates
    2. Window count
    3. Each window

Title and description come from the user's first message (Gemini writes
them; a plain-code fallback is used if Gemini is unavailable). A step is
skipped when the user already gave that detail.

Everything here is plain code: no Gemini, no database. Replies to these
questions ("everyday", "2", "9 am to 11 am") are read directly, which is
why they answer instantly.

Progress that is not part of the task itself (how many windows the user
asked for, a time waiting for AM/PM) lives in `collect`, stored inside the
draft next to the task.
"""

import re
from copy import deepcopy
from datetime import date

from src.modules.assistant.slot_filler import (
    extract_count,
    extract_duration,
    extract_meridiem,
    extract_repeat,
    extract_task_fields,
    extract_title,
    fill_gaps,
    find_dates,
    parse_reminder_windows,
)


CREATE_ACTIONS = {"create_repeat_until_done_task", "create_recurring_task"}
MAX_WINDOWS = 5


# =========================================================
# FORMATTING HELPERS
# =========================================================

def _pretty_date(value):
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _pretty_time(hhmm):
    try:
        hour, minute = map(int, str(hhmm).split(":"))
    except ValueError:
        return str(hhmm)
    suffix = "AM" if hour < 12 else "PM"
    shown = hour % 12 or 12
    return f"{shown}:{minute:02d} {suffix}"


def _pretty_window(window):
    start = window.get("start_time")
    end = window.get("end_time")
    count = window.get("count", 1)
    one_minute = False
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        one_minute = (eh * 60 + em) - (sh * 60 + sm) == 1
    except (ValueError, AttributeError):
        pass
    if one_minute and count == 1:
        return f"at {_pretty_time(start)}"
    text = f"{_pretty_time(start)} - {_pretty_time(end)}"
    if count and count > 1:
        text += f" ({count} reminders)"
    return text


_REPEAT_NAMES = {
    "everyday": "every day",
    "weekdays": "on weekdays",
    "weekends": "on weekends",
    "custom_dates": "on selected dates",
}


def build_summary(action, task):
    """One readable line for the confirmation card."""

    title = task.get("title") or "Task"
    kind = "recurring task" if action == "create_recurring_task" else "Repeat Until Done task"
    parts = [f"Create {kind} \"{title}\""]

    repeat = (task.get("repeat") or {}).get("type")
    if repeat:
        parts.append(_REPEAT_NAMES.get(repeat, repeat))

    duration = task.get("duration") or {}
    if duration.get("start_date") and duration.get("end_date"):
        parts.append(
            f"from {_pretty_date(duration['start_date'])} to {_pretty_date(duration['end_date'])}"
        )

    windows = task.get("reminders") or []
    if windows:
        parts.append("reminders " + ", ".join(_pretty_window(w) for w in windows))

    return ", ".join(parts) + "."


def default_description(title):
    """Fallback when Gemini did not write a description."""
    if not title:
        return ""
    return f"Reminder to {title[0].lower()}{title[1:]}."


# =========================================================
# WHAT TO ASK NEXT
# =========================================================

def _windows(task):
    value = task.get("reminders")
    return value if isinstance(value, list) else []


def next_step(action, task, collect):
    """Return {"field", "question", "suggestions"} or None when complete."""

    collect = collect or {}

    if not str(task.get("title") or "").strip():
        return {
            "field": "title",
            "question": "What should I call this task?",
            "suggestions": [],
        }

    duration = task.get("duration") if isinstance(task.get("duration"), dict) else {}
    start = duration.get("start_date")
    end = duration.get("end_date")

    # ---- 1. Dates (recurring only) -----------------------------------
    if action == "create_recurring_task":
        if not start and not end:
            return {
                "field": "duration",
                "question": (
                    "What are the start and end dates? For example: "
                    "\"from today to 15 Oct\" or \"starting tomorrow for 2 weeks\"."
                ),
                "suggestions": ["Today for 1 week", "Today for 2 weeks", "Today for 1 month"],
            }
        if not start:
            return {
                "field": "duration.start_date",
                "question": f"It ends on {_pretty_date(end)}. When should it start?",
                "suggestions": ["Today", "Tomorrow"],
            }
        if not end:
            return {
                "field": "duration.end_date",
                "question": (
                    f"It starts on {_pretty_date(start)}. When should it end? "
                    "You can give a date or a length like \"2 weeks\"."
                ),
                "suggestions": ["For 1 week", "For 2 weeks", "For 1 month"],
            }

    # ---- 2. Repeat ------------------------------------------------------
    repeat = task.get("repeat") if isinstance(task.get("repeat"), dict) else {}
    if not repeat.get("type"):
        if action == "create_recurring_task":
            question = (
                f"How should it repeat between {_pretty_date(start)} and "
                f"{_pretty_date(end)}: every day, weekdays, weekends, or custom dates?"
            )
        else:
            question = (
                "How often should I remind you until it's done: every day, "
                "weekdays, weekends, or custom dates?"
            )
        return {
            "field": "repeat",
            "question": question,
            "suggestions": ["Every day", "Weekdays", "Weekends", "Custom dates"],
        }

    if repeat.get("type") == "custom_dates" and not repeat.get("custom_dates"):
        where = (
            f" (between {_pretty_date(start)} and {_pretty_date(end)})"
            if action == "create_recurring_task"
            else ""
        )
        return {
            "field": "repeat.custom_dates",
            "question": f"Which dates{where}? For example: 25 Sep, 27 Sep and 2 Oct.",
            "suggestions": [],
        }

    # ---- 3. A time is waiting for AM/PM --------------------------------
    if collect.get("pending_times_text"):
        label = collect.get("pending_times_label") or "that time"
        return {
            "field": "reminders.meridiem",
            "question": f"Is {label} AM or PM?",
            "suggestions": ["AM", "PM"],
        }

    # ---- 4. How many reminder windows -----------------------------------
    windows = _windows(task)
    count = collect.get("window_count")

    if count is None and not windows:
        return {
            "field": "reminders.count",
            "question": "How many reminder windows do you want each day? (1 to 5)",
            "suggestions": ["1", "2", "3"],
        }

    # ---- 5. Start and end time for each window --------------------------
    if count and len(windows) < count:
        number = len(windows) + 1
        prefix = (
            "What start and end time should the reminder window have?"
            if count == 1
            else f"Reminder window {number} of {count}: what start and end time?"
        )
        return {
            "field": "reminders.window",
            "question": prefix + " For example: 9 am to 11 am.",
            "suggestions": [],
        }

    return None


RETRY_QUESTIONS = {
    "title": "I still need a name for this task. Just type the name, for example: Buy groceries.",
    "duration": (
        "Sorry, I didn't get the dates. Try: \"from 25 Sep to 10 Oct\", "
        "\"today for 2 weeks\", or \"starting tomorrow for 30 days\"."
    ),
    "duration.start_date": "When should it start? For example: today, tomorrow, or 1 Oct.",
    "duration.end_date": "When should it end? For example: 15 Oct, or a length like 2 weeks.",
    "repeat": (
        "Sorry, I didn't catch that. Reply with one of: every day, weekdays, "
        "weekends, or custom dates."
    ),
    "repeat.custom_dates": "Which dates? For example: 25 Sep, 27 Sep and 2 Oct.",
    "reminders.meridiem": "Please reply AM or PM.",
    "reminders.count": "How many reminder windows? Reply with a number from 1 to 5.",
    "reminders.window": (
        "Sorry, I didn't get the times. Give a start and end time with AM/PM, "
        "for example: 9 am to 11 am, or 18:00 to 19:30."
    ),
}


# =========================================================
# READING AN ANSWER
# =========================================================

def _set_windows(task, collect, windows):
    """Add new windows, never exceeding what the user asked for."""
    current = _windows(task)
    merged = current + [w for w in windows if w not in current]
    count = collect.get("window_count")
    if count is None or len(merged) > count:
        collect["window_count"] = min(len(merged), MAX_WINDOWS)
    task["reminders"] = merged[:MAX_WINDOWS]


def _ambiguous_label(text, lenient):
    """The exact time(s) that need AM/PM, for the question."""
    labels = []
    parse_reminder_windows(text, lenient=lenient, labels=labels)
    if not labels:
        return "that time"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _hold_for_meridiem(collect, text, lenient):
    collect["pending_times_text"] = text
    collect["pending_times_lenient"] = lenient
    collect["pending_times_label"] = _ambiguous_label(text, lenient)


def _end_from(reply, start, today):
    """End date from an answer when the start date is already known."""
    text = str(reply or "").lower()
    base = date.fromisoformat(start)
    length = extract_duration(text, base)
    has_length = re.search(r"\b\d+\s*(day|week|month)|\b(a|one)\s+(day|week|month)|fortnight", text)
    if length and has_length and length.get("start_date") == base.isoformat():
        return length.get("end_date")
    dates = find_dates(text, today)
    return dates[-1].isoformat() if dates else None


def apply_answer(field, action, task, collect, reply, today):
    """
    Read the user's reply to the question about `field`.

    Returns (task, collect, understood).
    """

    task = deepcopy(task) if isinstance(task, dict) else {}
    collect = dict(collect or {})
    understood = False

    if field == "title":
        title = extract_title(reply)
        if title:
            task["title"] = title
            understood = True

    elif field in ("duration", "duration.start_date", "duration.end_date"):
        duration = dict(task.get("duration") or {})

        if field == "duration.start_date":
            dates = find_dates(reply, today)
            if dates:
                duration["start_date"] = dates[0].isoformat()
                understood = True

        elif field == "duration.end_date" and duration.get("start_date"):
            end = _end_from(reply, duration["start_date"], today)
            if end:
                duration["end_date"] = end
                understood = True

        else:
            dates = find_dates(reply, today)
            explicit = extract_duration(reply, today)
            if explicit:
                duration.update(explicit)
                understood = True
            elif len(dates) == 1:
                # One date answering "start and end?" is the start date;
                # we ask for the end next.
                duration["start_date"] = dates[0].isoformat()
                understood = True
            else:
                loose = extract_duration(reply, today, lenient=True)
                if loose:
                    duration.update(loose)
                    understood = True

        if duration.get("start_date") and duration.get("end_date"):
            if duration["end_date"] < duration["start_date"]:
                # Keep the start, drop an impossible end, ask again.
                duration.pop("end_date")
                understood = False
        task["duration"] = duration

    elif field in ("repeat", "repeat.custom_dates"):
        repeat = extract_repeat(reply)
        dates = sorted({d.isoformat() for d in find_dates(reply, today)})
        current = task.get("repeat") if isinstance(task.get("repeat"), dict) else {}

        if repeat and repeat["type"] != "custom_dates":
            task["repeat"] = repeat
            understood = True
        elif dates and (field == "repeat.custom_dates" or current.get("type") == "custom_dates" or repeat or field == "repeat"):
            task["repeat"] = {"type": "custom_dates", "custom_dates": dates}
            understood = True
        elif repeat:
            task["repeat"] = repeat  # custom dates, which ones asked next
            understood = True

    elif field == "reminders.meridiem":
        # They may simply retype the time with AM/PM.
        windows, ambiguous = parse_reminder_windows(reply, lenient=True)
        if windows and not ambiguous:
            _set_windows(task, collect, windows)
            understood = True
        else:
            hint = extract_meridiem(reply)
            if hint:
                windows, ambiguous = parse_reminder_windows(
                    collect.get("pending_times_text", ""),
                    lenient=bool(collect.get("pending_times_lenient", True)),
                    hint=hint,
                )
                if windows:
                    _set_windows(task, collect, windows)
                    understood = True
        if understood:
            for key in ("pending_times_text", "pending_times_lenient", "pending_times_label"):
                collect.pop(key, None)

    elif field == "reminders.count":
        # Times given straight away ("9 am to 11 am") answer this step too.
        windows, ambiguous = parse_reminder_windows(reply)
        if windows:
            _set_windows(task, collect, windows)
            understood = True
        elif ambiguous:
            collect["window_count"] = collect.get("window_count") or 1
            _hold_for_meridiem(collect, reply, False)
            understood = True
        else:
            count = extract_count(reply)
            if count:
                collect["window_count"] = min(count, MAX_WINDOWS)
                understood = True

    elif field == "reminders.window":
        windows, ambiguous = parse_reminder_windows(reply, lenient=True)
        if ambiguous:
            _hold_for_meridiem(collect, reply, True)
            understood = True
        elif windows:
            _set_windows(task, collect, windows)
            understood = True

    if understood:
        # Extra details in the same reply ("every day at 9 am") fill
        # other empty fields too -- but never overwrite what we have.
        extra = extract_task_fields(reply, today)
        if field.startswith("reminders"):
            extra.pop("reminders", None)
        task = fill_gaps(task, extra, action)
        if extra.get("reminders") and collect.get("window_count") is None:
            collect["window_count"] = len(task.get("reminders") or [])

    return task, collect, understood


# =========================================================
# FIRST MESSAGE
# =========================================================

def prefill_from_message(action, task, collect, message, today):
    """
    After Gemini has read the first message, top up anything it missed and
    refuse to trust any time that was missing AM/PM.
    """

    task = deepcopy(task) if isinstance(task, dict) else {}
    collect = dict(collect or {})

    windows, ambiguous = parse_reminder_windows(message)
    if ambiguous:
        # Gemini had to guess AM or PM for something like "at 4:22".
        # Drop the guess and ask.
        task.pop("reminders", None)
        collect["window_count"] = collect.get("window_count") or 1
        _hold_for_meridiem(collect, message, False)

    task = fill_gaps(task, extract_task_fields(message, today), action)

    if action != "create_recurring_task":
        task.pop("duration", None)

    if _windows(task) and collect.get("window_count") is None:
        collect["window_count"] = len(_windows(task))

    return task, collect


# =========================================================
# GEMINI UNAVAILABLE: READ THE FIRST MESSAGE LOCALLY
# =========================================================

_CUTOFF = re.compile(
    r"\s+(?:starting|start|from|for the next|for|every|each|daily|weekdays|weekends"
    r"|at|on|until|till|by|tomorrow|today|between)\b",
    re.IGNORECASE,
)


def local_title(message):
    text = str(message or "").strip()

    named = re.search(
        r"\b(?:called|named|titled)\s+[\"'“]?(.+?)[\"'”]?(?=\s+(?:starting|from|for|every|each|daily"
        r"|on|at|until|till|by|weekdays|weekends)\b|[,.]|$)",
        text,
        re.IGNORECASE,
    )
    if named:
        text = named.group(1)
    else:
        text = re.sub(r"^(please\s+)?(can you\s+|could you\s+)?", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^(create|add|make|schedule|set up|setup|new|remind me to|remind me|"
            r"i need to|i have to|i want to)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^(a|an|the|new|my)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^(recurring|repeat[- ]until[- ]done|repeating|daily)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^(task|reminder)\s+(to|for)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+(task|reminder|todo|to-do)\b", "", text, flags=re.IGNORECASE)
        cut = _CUTOFF.search(text)
        if cut:
            text = text[: cut.start()]

    text = text.strip(" .,'\"“”")
    if not text:
        return None
    return text[0].upper() + text[1:]


def local_intent(message, today):
    """
    Best-effort reading of a task request without Gemini.

    Used only when Gemini is overloaded, so the user can still create a
    task. The confirmation card shows everything before it is saved.
    Returns None when the message is not clearly a create request.
    """

    text = str(message or "").strip().lower()

    if re.search(r"\b(show|list|what are|what's|how many)\b.*\btasks?\b", text):
        return {"action": "list_active_tasks", "arguments": {}}

    if not re.search(
        r"^(please\s+)?(create|add|make|schedule|set up|setup|new|remind me)\b"
        r"|\btask\b|\breminder\b",
        text,
    ):
        return None

    if re.search(r"^(please\s+)?(edit|update|change|rename|reschedule|delete|remove|complete|finish|mark)\b", text):
        return None

    has_dates = bool(extract_duration(text, today))
    wants_recurring = bool(
        re.search(r"\b(recurring|habit|routine)\b", text)
    ) and not re.search(r"repeat[- ]until[- ]done", text)

    action = (
        "create_recurring_task"
        if has_dates or wants_recurring
        else "create_repeat_until_done_task"
    )

    task = {}
    title = local_title(message)
    if title:
        task["title"] = title
        task["description"] = default_description(title)

    return {"action": action, "arguments": {"task": task}}
