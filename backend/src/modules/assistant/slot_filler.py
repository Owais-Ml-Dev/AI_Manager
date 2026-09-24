"""Deterministic extraction of task fields from plain text.

Why this exists
---------------
When the assistant asks a follow-up question ("How often should this task
repeat?"), the answer is usually one or two words: "everyday", "9 am",
"for 2 weeks". Sending that to Gemini is slow (a full API round trip) and
unreliable (a one-word message has no context, so the model can drop it).

These answers are easy to read with plain code. This module holds the
readers (dates, repeat words, reminder times, durations, titles). The step
order that uses them lives in create_flow.py.

    extract_task_fields(text, today)
        -> pulls repeat / reminders / duration out of any message; used to
           fill gaps Gemini left empty (never to override Gemini)

Nothing here touches the database or calls Gemini.
"""

import re
from copy import deepcopy
from datetime import date, timedelta


# =========================================================
# SMALL HELPERS
# =========================================================

_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "thirty": 30,
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

_NUMBER = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|fifteen|twenty|thirty)"
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_NAMES = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _to_number(token):
    token = str(token).lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp the day for short months (Jan 31 + 1 month -> Feb 28/29).
    for day in (start.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


# =========================================================
# DATES
# =========================================================

_DATE_PATTERNS = [
    # 2026-09-25
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
]

_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({_MONTH_NAMES})\b(?:\s+(\d{{4}}))?"
)
_MONTH_DAY = re.compile(
    rf"\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?"
)
# 25/09 or 25/09/2026 -- day first (India / UK convention).
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_WEEKDAY_DATE = re.compile(rf"\b(?:next\s+|this\s+|on\s+)?({_WEEKDAY_NAMES})\b")


def _future_date(year, month, day, today):
    """Build a date; if no year was given and it already passed, use next year."""
    try:
        if year is None:
            candidate = date(today.year, month, day)
            if candidate < today:
                candidate = date(today.year + 1, month, day)
            return candidate
        year = int(year)
        if year < 100:
            year += 2000
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text, today):
    """Return every explicit date mentioned, in order of appearance."""

    text = _clean(text)
    found = []  # (position, date)

    for match in _DATE_PATTERNS[0].finditer(text):
        try:
            found.append((match.start(), date(int(match.group(1)), int(match.group(2)), int(match.group(3)))))
        except ValueError:
            pass

    for match in _DAY_MONTH.finditer(text):
        value = _future_date(match.group(3), _MONTHS[match.group(2)], int(match.group(1)), today)
        if value:
            found.append((match.start(), value))

    for match in _MONTH_DAY.finditer(text):
        value = _future_date(match.group(3), _MONTHS[match.group(1)], int(match.group(2)), today)
        if value:
            found.append((match.start(), value))

    for match in _SLASH_DATE.finditer(text):
        value = _future_date(match.group(3), int(match.group(2)), int(match.group(1)), today)
        if value:
            found.append((match.start(), value))

    for match in re.finditer(r"\bday after tomorrow\b", text):
        found.append((match.start(), today + timedelta(days=2)))

    for match in re.finditer(r"\btomorrow\b", text):
        # Skip the "tomorrow" inside "day after tomorrow".
        if text[max(0, match.start() - 10):match.start()].endswith("after "):
            continue
        found.append((match.start(), today + timedelta(days=1)))

    for match in re.finditer(r"\btoday\b", text):
        found.append((match.start(), today))

    for match in _WEEKDAY_DATE.finditer(text):
        # "weekdays"/"weekends" are repeat words, not dates.
        word = match.group(1)
        tail = text[match.end():match.end() + 1]
        if tail.isalpha():
            continue
        target = _WEEKDAYS[word]
        delta = (target - today.weekday()) % 7
        if match.group(0).startswith("next") and delta == 0:
            delta = 7
        found.append((match.start(), today + timedelta(days=delta)))

    found.sort(key=lambda item: item[0])

    unique = []
    seen = set()
    for _, value in found:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


# =========================================================
# REPEAT
# =========================================================

def extract_repeat(text):
    """'everyday' -> {'type': 'everyday', 'custom_dates': []}"""

    text = _clean(text)
    if not text:
        return None

    if re.search(
        r"\b(weekends?|week ends?|sat(urday)?s?\s*(and|&|,)\s*sun(day)?s?)\b",
        text,
    ):
        return {"type": "weekends", "custom_dates": []}

    if re.search(
        r"\b(weekdays?|week days?|working days?|work ?days?|business days?"
        r"|mon(day)?\s*(-|to|through|till|until)\s*fri(day)?)\b",
        text,
    ):
        return {"type": "weekdays", "custom_dates": []}

    if re.search(
        r"\b(every ?day|everyday|daily|each day|all days|every single day"
        r"|once a day|day by day)\b",
        text,
    ):
        return {"type": "everyday", "custom_dates": []}

    if re.search(r"\b(specific|particular|certain|custom|selected) (dates?|days?)\b", text):
        return {"type": "custom_dates", "custom_dates": []}

    return None


# =========================================================
# REMINDER TIMES
# =========================================================
#
# A time like "4:22" is ambiguous: 4:22 AM or 4:22 PM? The old code quietly
# picked AM. Now a time only counts as clear when it has am/pm, or it can
# only be 24-hour (13:00-23:59, 00:xx, or a leading zero like 09:30).
# Anything else is reported as ambiguous so the assistant can ask.

_TOK = r"(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?"

# "9-11 am", "9 am to 11 am", "09:00 till 11:00", "between 9 and 11"
_RANGE = re.compile(
    rf"(?<![\d/:.-])(between\s+)?{_TOK}\s*(-|–|to|till|until|and)\s*{_TOK}(?![\d/:])"
)

_SINGLE = re.compile(rf"(?<![\d/:.-]){_TOK}(?![\d/:])")

_TIMES_COUNT = re.compile(rf"\b{_NUMBER}\s+(?:times?|reminders?)\b|\b(once|twice|thrice)\b")

# Words after a number that mean it is NOT a clock time.
_NOT_TIME_AFTER = re.compile(
    r"^\s*(days?|weeks?|months?|years?|times?|mins?|minutes?|hours?|hrs?"
    r"|windows?|reminders?|st\b|nd\b|rd\b|th\b|of\b|"
    + _MONTH_NAMES
    + r")"
)


def _mer(value):
    if not value:
        return None
    return "pm" if value.replace(".", "").replace(" ", "").startswith("p") else "am"


def _clock(hour_text, minute_text, meridiem, hint=None):
    """Return ("HH:MM", ambiguous_flag). ("", False) means invalid."""

    hour = int(hour_text)
    minute = int(minute_text or 0)
    if minute > 59:
        return "", False

    if meridiem:
        if hour < 1 or hour > 12:
            return "", False
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}", False

    if hour > 23:
        return "", False

    clearly_24h = hour == 0 or hour >= 13 or (len(hour_text) == 2 and hour_text.startswith("0"))
    if clearly_24h:
        return f"{hour:02d}:{minute:02d}", False

    if hint:
        return _clock(hour_text, minute_text, hint)

    return f"{hour:02d}:{minute:02d}", True


def _plus_minute(hhmm):
    hour, minute = map(int, hhmm.split(":"))
    total = hour * 60 + minute + 1
    return f"{total // 60:02d}:{total % 60:02d}"


def _point_window(hhmm):
    """A single time becomes a one-minute window (backend needs start < end)."""
    if hhmm >= "23:59":
        return {"start_time": "23:58", "end_time": "23:59", "count": 1}
    return {"start_time": hhmm, "end_time": _plus_minute(hhmm), "count": 1}


def _range_window(match, hint):
    between, h1, m1, a1, connector, h2, m2, a2 = match.groups()
    if connector == "and" and not between:
        return None, False

    mer1, mer2 = _mer(a1), _mer(a2)

    # One side says am/pm: carry it over sensibly.
    #   "9 to 11 am" -> both am.   "11 to 2 pm" -> 11 am to 2 pm.
    #   "9 am to 11" -> both am.   "11 am to 1" -> 11 am to 1 pm.
    if mer2 and not mer1 and 1 <= int(h1) <= 12:
        mer1 = mer2
        if mer2 == "pm" and int(h1) != 12 and int(h1) > int(h2):
            mer1 = "am"
    if mer1 and not mer2 and 1 <= int(h2) <= 12:
        mer2 = mer1
        if int(h2) < int(h1) or (int(h2) == int(h1) and int(m2 or 0) <= int(m1 or 0)):
            mer2 = "pm" if mer1 == "am" else "am"

    def _is_24h(hour_text):
        hour = int(hour_text)
        return hour == 0 or hour >= 13 or (len(hour_text) == 2 and hour_text.startswith("0"))

    # "09:30 - 10:00", "18:00 to 9:30": one side is plainly 24-hour, so the
    # other side is 24-hour too.
    if not mer1 and not mer2 and (_is_24h(h1) or _is_24h(h2)):
        if int(h1) > 23 or int(h2) > 23 or int(m1 or 0) > 59 or int(m2 or 0) > 59:
            return None, False
        start = f"{int(h1):02d}:{int(m1 or 0):02d}"
        end = f"{int(h2):02d}:{int(m2 or 0):02d}"
        if start >= end:
            return None, False
        return {"start_time": start, "end_time": end, "count": 1}, False

    start, amb1 = _clock(h1, m1, mer1, hint)
    end, amb2 = _clock(h2, m2, mer2, hint)
    if not start or not end:
        return None, False
    if amb1 or amb2:
        return None, True

    if start >= end and hint and int(h2) < 12:
        # "11 to 2" + pm hint -> 11:00 to 14:00
        end, _ = _clock(h2, m2, "pm")
        if start >= end:
            start, _ = _clock(h1, m1, "am")
    if start >= end:
        return None, False

    return {"start_time": start, "end_time": end, "count": 1}, False


def parse_reminder_windows(text, lenient=False, hint=None, labels=None):
    """
    Read reminder windows from text.

    Returns (windows, ambiguous):
        windows    list of {"start_time", "end_time", "count"} or None
        ambiguous  True when a time is missing AM/PM ("4:22", "9 to 11").
                   Nothing is guessed; the caller asks the user.

    lenient=False (a normal sentence): a bare number such as the 7 in
        "7 days" is ignored. Times need am/pm, minutes, or "at".
    lenient=True (we just asked for a time): a bare "9" counts as a time.
    hint="am"/"pm": the user's answer to "AM or PM?".
    labels: optional list; the ambiguous pieces of text are appended to it
        (used to ask "Is 4:22 AM or PM?").
    """

    text = _clean(text)
    if not text:
        return None, False

    text = re.sub(r"\bnoon\b|\bmidday\b", "12:00 pm", text)
    text = re.sub(r"\bmidnight\b", "12:00 am", text)
    text = re.sub(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*o'?\s?clock\b", lambda m: m.group(0).split("o")[0].strip(), text)

    windows = []
    ambiguous = False
    used = []

    for match in _RANGE.finditer(text):
        window, amb = _range_window(match, hint)
        if amb:
            ambiguous = True
            used.append(match.span())
            if labels is not None:
                labels.append(match.group(0).replace("between ", "").strip())
        elif window:
            windows.append(window)
            used.append(match.span())

    for match in _SINGLE.finditer(text):
        if any(start <= match.start() < end for start, end in used):
            continue
        hour, minute, meridiem = match.groups()
        after = text[match.end():]
        before = text[:match.start()]
        if _NOT_TIME_AFTER.match(after):
            continue
        clear = bool(meridiem or minute or re.search(r"\b(at|@)\s*$", before))
        if not clear and not lenient:
            continue
        hhmm, amb = _clock(hour, minute, _mer(meridiem), hint)
        if not hhmm:
            continue
        if amb:
            ambiguous = True
            if labels is not None:
                labels.append(match.group(0).strip())
            continue
        windows.append(_point_window(hhmm))

    if ambiguous:
        return None, True

    # "3 times" applies when the user described a single window.
    count_match = _TIMES_COUNT.search(text)
    if count_match and len(windows) == 1:
        word = count_match.group(1) or count_match.group(2)
        count = {"once": 1, "twice": 2, "thrice": 3}.get(word) or _to_number(word) or 1
        windows[0]["count"] = max(1, min(int(count), 20))

    unique = []
    seen = set()
    for window in sorted(windows, key=lambda item: item["start_time"]):
        key = (window["start_time"], window["end_time"])
        if key not in seen:
            seen.add(key)
            unique.append(window)

    return (unique or None), False


def extract_reminders(text, lenient=False, hint=None):
    """Backward-compatible wrapper: windows only, None when unclear."""
    windows, _ = parse_reminder_windows(text, lenient=lenient, hint=hint)
    return windows


def extract_count(text):
    """'2', 'two', '2 windows', 'just one' -> int (1..10) or None."""
    text = _clean(text)
    match = re.search(rf"\b{_NUMBER}\b", text)
    if not match:
        return None
    value = _to_number(match.group(1))
    if value is None or not (1 <= value <= 10):
        return None
    return value


def extract_meridiem(text):
    text = _clean(text)
    if re.search(r"\b(p\.?\s?m\.?|evening|night|afternoon)\b", text):
        return "pm"
    if re.search(r"\b(a\.?\s?m\.?|morning)\b", text):
        return "am"
    return None


# =========================================================
# DURATION (recurring tasks)
# =========================================================

def _leading_date(text, today):
    """Return the date that the text STARTS with, or None."""

    text = _clean(text)
    text = re.sub(r"^(the|on)\s+", "", text)

    if text.startswith("day after tomorrow"):
        return today + timedelta(days=2)
    if text.startswith("tomorrow"):
        return today + timedelta(days=1)
    if text.startswith("today") or text.startswith("now"):
        return today

    for pattern in (_DATE_PATTERNS[0], _DAY_MONTH, _MONTH_DAY, _SLASH_DATE):
        if pattern.match(text):
            dates = find_dates(text[: pattern.match(text).end()], today)
            if dates:
                return dates[0]

    weekday = re.match(rf"(?:next\s+|this\s+)?({_WEEKDAY_NAMES})\b", text)
    if weekday:
        dates = find_dates(weekday.group(0), today)
        if dates:
            return dates[0]

    return None


_LENGTH = re.compile(
    rf"\b(?:for\s+)?(?:the\s+)?(?:next\s+)?{_NUMBER}\s+(days?|weeks?|months?)\b"
)
_A_UNIT = re.compile(r"\b(?:for\s+)?(?:(?:a|one|the next|next)\s+)?(fortnight)\b|\b(?:for\s+)?(?:a|one|the next|next)\s+(day|week|month)\b")
_UNTIL = re.compile(r"\b(?:until|till|til|through|to|up to|upto|ending|ends?)\b")
_START = re.compile(r"\b(?:from|starting|start|starts|beginning|begin)\b")


def extract_duration(text, today, lenient=False):
    """
    Read a recurring task's date range.

    'for 7 days'              -> today .. today+6
    'starting tomorrow for 2 weeks'
    'until 30 sep' / 'till 2026-10-01'
    'from 1 oct to 15 oct'

    Returns {'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD'} with only
    the keys it could determine.
    """

    text = _clean(text)
    if not text:
        return None

    result = {}

    # Explicit start: a date directly after a start word ("from 1 oct").
    start_date = None
    for start_word in _START.finditer(text):
        start_date = _leading_date(text[start_word.end():], today)
        if start_date:
            break

    # Explicit end: a date directly after an until word ("till 15 oct").
    # "Directly" matters: in "remind me to study tomorrow", "to" is not
    # followed by a date, so tomorrow must not become the end date.
    end_date = None
    for until in _UNTIL.finditer(text):
        end_date = _leading_date(text[until.end():], today)
        if end_date:
            # "25 sep to 5 oct": the date right before "to" is the start.
            if start_date is None:
                before = find_dates(text[: until.start()], today)
                if before:
                    start_date = before[-1]
            break

    # Length: "for 7 days", "2 weeks", "a month", "a fortnight"
    days = None
    length = _LENGTH.search(text)
    if length:
        amount = _to_number(length.group(1))
        unit = length.group(2)
        if amount:
            if unit.startswith("day"):
                days = amount
            elif unit.startswith("week"):
                days = amount * 7
            else:
                days = ("months", amount)
    else:
        a_unit = _A_UNIT.search(text)
        if a_unit:
            unit = a_unit.group(1) or a_unit.group(2)
            days = {"day": 1, "week": 7, "fortnight": 14}.get(unit, ("months", 1))

    # Only a single loose date and nothing else ("tomorrow", "25 sep"):
    if start_date is None and end_date is None and days is None and lenient:
        loose = find_dates(text, today)
        if len(loose) >= 2:
            start_date, end_date = loose[0], loose[1]
        elif len(loose) == 1:
            # "25 sep" answering "how long?" is an end date.
            end_date = loose[0]

    if start_date is None and (days is not None or end_date is not None):
        # A length or an end without a start means "starting today" --
        # unless the message clearly says tomorrow etc. without a start word.
        loose = find_dates(text, today)
        if days is not None and loose and end_date is None:
            start_date = loose[0]
        else:
            start_date = today

    if start_date is not None and end_date is None and days is not None:
        if isinstance(days, tuple):
            end_date = _add_months(start_date, days[1]) - timedelta(days=1)
        else:
            end_date = start_date + timedelta(days=max(days, 1) - 1)

    if start_date is not None:
        result["start_date"] = start_date.isoformat()
    if end_date is not None:
        result["end_date"] = end_date.isoformat()

    return result or None


# =========================================================
# TITLE (only when the assistant explicitly asked for it)
# =========================================================

def extract_title(text):
    value = str(text or "").strip()
    value = re.sub(
        r"^(?:please\s+)?(?:call it|name it|title it|it'?s called|the title is|title:?|name:?)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = value.strip().strip("\"'“”‘’").strip()
    if not value or len(value) > 120:
        return None
    return value[0].upper() + value[1:]


# =========================================================
# PUBLIC API
# =========================================================

def extract_task_fields(text, today):
    """Pull whatever is clearly stated. Strict mode: no guessing."""

    fields = {}

    repeat = extract_repeat(text)
    if repeat:
        fields["repeat"] = repeat

    windows, _ = parse_reminder_windows(text)
    if windows:
        fields["reminders"] = windows

    duration = extract_duration(text, today)
    if duration:
        fields["duration"] = duration

    return fields


def _is_empty(value):
    return value in (None, "", [], {})


def fill_gaps(task, extracted, action=None):
    """Copy extracted fields into `task` only where `task` has nothing."""

    result = deepcopy(task) if isinstance(task, dict) else {}

    for key, value in (extracted or {}).items():
        if key == "duration" and action not in {
            "create_recurring_task",
            "create_repeat_until_done_task",
        }:
            continue

        if key == "duration":
            current = result.get("duration") if isinstance(result.get("duration"), dict) else {}
            merged = dict(current)
            for sub_key, sub_value in value.items():
                if _is_empty(merged.get(sub_key)):
                    merged[sub_key] = sub_value
            result["duration"] = merged
            continue

        if key == "repeat":
            current = result.get("repeat")
            if not isinstance(current, dict) or not current.get("type"):
                result["repeat"] = deepcopy(value)
            continue

        if _is_empty(result.get(key)):
            result[key] = deepcopy(value)

    return result
