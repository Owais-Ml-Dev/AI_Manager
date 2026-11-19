"""Unit tests for pure, deterministic logic — no database, no network.

Covers the date rules every reminder/occurrence depends on, request
validation (including the null-PATCH bug), and small pure helpers.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.features.assistant.schemas import Intent, PendingAction, ConversationState
from app.features.assistant.service import _confirmation_message, _missing_required
from app.features.reminders.models import DaySelectionType, ReminderConfig
from app.features.reminders.schemas import ReminderConfigWrite
from app.features.reminders.service import compute_eligible_dates
from app.features.reports.service import _month_range
from app.features.tasks.schemas import TaskCreate, TaskUpdate
from app.features.tasks.service import _quadrant_key

MON = date(2026, 11, 16)  # a Monday
SUN = date(2026, 11, 22)


def config(kind, start=MON, end=SUN, weekdays=None, dates=None):
    return ReminderConfig(
        start_date=start,
        end_date=end,
        day_selection_type=kind,
        custom_weekdays=weekdays,
        custom_dates=dates,
    )


# --- compute_eligible_dates -------------------------------------------------

def test_every_day_covers_whole_range():
    assert len(compute_eligible_dates(config(DaySelectionType.EVERY_DAY), SUN)) == 7


def test_weekdays_are_monday_to_friday():
    result = compute_eligible_dates(config(DaySelectionType.WEEKDAYS), SUN)
    assert [d.isoweekday() for d in result] == [1, 2, 3, 4, 5]


def test_weekends_are_saturday_and_sunday():
    result = compute_eligible_dates(config(DaySelectionType.WEEKENDS), SUN)
    assert [d.isoweekday() for d in result] == [6, 7]


def test_custom_weekdays():
    result = compute_eligible_dates(config(DaySelectionType.CUSTOM_WEEKDAYS, weekdays=[1, 3, 5]), SUN)
    assert [d.isoweekday() for d in result] == [1, 3, 5]


def test_custom_dates_outside_range_are_dropped():
    dates = [date(2026, 11, 18), date(2026, 12, 25)]
    result = compute_eligible_dates(config(DaySelectionType.CUSTOM_DATES, dates=dates), SUN)
    assert result == [date(2026, 11, 18)]


def test_cap_date_limits_an_open_ended_config():
    result = compute_eligible_dates(config(DaySelectionType.EVERY_DAY, end=None), date(2026, 11, 18))
    assert result[-1] == date(2026, 11, 18)


def test_cap_before_start_gives_nothing():
    assert compute_eligible_dates(config(DaySelectionType.EVERY_DAY), date(2026, 11, 1)) == []


# --- reminder config validation --------------------------------------------

def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        ReminderConfigWrite(start_date=SUN, end_date=MON, day_selection_type="every_day")


def test_custom_weekdays_required_and_in_range():
    with pytest.raises(ValidationError):
        ReminderConfigWrite(start_date=MON, day_selection_type="custom_weekdays")
    with pytest.raises(ValidationError):
        ReminderConfigWrite(start_date=MON, day_selection_type="custom_weekdays", custom_weekdays=[8])


def test_custom_fields_rejected_for_plain_types():
    with pytest.raises(ValidationError):
        ReminderConfigWrite(start_date=MON, day_selection_type="every_day", custom_weekdays=[1])


def test_end_date_optional_at_schema_level():
    assert ReminderConfigWrite(start_date=MON, day_selection_type="every_day").end_date is None


# --- task validation --------------------------------------------------------

def test_due_date_rejected_for_recurring():
    with pytest.raises(ValidationError):
        TaskCreate(title="x", category="recurring", urgent=False, important=False, due_date=MON)


def test_due_time_requires_due_date():
    with pytest.raises(ValidationError):
        TaskCreate(title="x", category="one_time", urgent=False, important=False, due_time="09:00")


@pytest.mark.parametrize("field", ["title", "urgent", "important", "status"])
def test_patch_rejects_null_for_non_nullable_fields(field):
    # Regression: these used to pass validation and 500 at the database.
    with pytest.raises(ValidationError):
        TaskUpdate(**{field: None})


def test_patch_allows_null_to_clear_nullable_fields():
    assert TaskUpdate(description=None, due_date=None).model_dump(exclude_unset=True) == {
        "description": None,
        "due_date": None,
    }


# --- small pure helpers ------------------------------------------------------

@pytest.mark.parametrize(
    "urgent,important,expected",
    [(True, True, "do_first"), (False, True, "schedule"), (True, False, "delegate"), (False, False, "eliminate")],
)
def test_quadrant_key(urgent, important, expected):
    assert _quadrant_key(SimpleNamespace(urgent=urgent, important=important)) == expected


def test_month_range_handles_december():
    assert _month_range(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))
    assert _month_range(2028, 2) == (date(2028, 2, 1), date(2028, 2, 29))


def test_assistant_lists_missing_details():
    P, I, S = PendingAction, Intent, ConversationState.IDLE
    assert _missing_required(P(state=S, intent=I.CREATE_TASK)) == ["title"]
    assert _missing_required(P(state=S, intent=I.CREATE_TASK, title="x", category="one_time")) == []
    # recurring needs its days; specific days need the weekdays
    assert _missing_required(P(state=S, intent=I.CREATE_TASK, title="x", category="recurring")) == ["day_selection"]
    assert _missing_required(P(state=S, intent=I.CREATE_TASK, title="x", category="recurring",
                               day_selection="custom_weekdays")) == ["weekdays"]
    # a reminder needs its time
    assert _missing_required(P(state=S, intent=I.CONFIGURE_REMINDER, title="x", day_selection="every_day")) == ["times"]


def test_assistant_confirmation_messages():
    from datetime import time

    P, S = PendingAction, ConversationState.IDLE
    one = P(state=S, intent=Intent.CREATE_TASK, title="Buy milk", category="one_time", due_date=MON)
    assert _confirmation_message(one, MON) == 'Create a one-time task "Buy milk", due 2026-11-16. Confirm?'
    rec = P(state=S, intent=Intent.CREATE_TASK, title="Swim", category="recurring",
            day_selection="custom_weekdays", weekdays=[2, 4], times=[time(6, 0), time(18, 30)])
    assert _confirmation_message(rec, MON) == (
        'Create recurring task "Swim": every Tue and Thu at 06:00 and 18:30, starting today. Confirm?')
    pause = P(state=S, intent=Intent.PAUSE_TASK, title="Swim")
    assert _confirmation_message(pause, MON).startswith('Pause "Swim"')


# --- voice-friendly replies (pure) ---------------------------------------------

def test_yes_no_replies_tolerate_speech_and_hinglish():
    from app.features.assistant.replies import is_no, is_yes

    for t in ["yes", "Yes.", "yes please", "yeah do it", "sure, go ahead", "ok confirm", "haan", "theek hai", "ji haan"]:
        assert is_yes(t) and not is_no(t), t
    for t in ["no", "No.", "no thanks", "nope", "cancel it", "never mind", "nahi", "mat karo", "ji nahi"]:
        assert is_no(t) and not is_yes(t), t
    # A changed request must never count as confirmation (or refusal).
    for t in ["yes but make it 8am", "yes delete the gym one", "no, yes", "move it to friday"]:
        assert not is_yes(t) and not is_no(t), t


def test_choice_replies():
    from app.features.assistant.replies import is_number_reply, parse_choice

    assert [parse_choice(t, 3) for t in ["2", "the second one", "number two", "dusra", "option 3", "first one"]] == [2, 2, 2, 2, 3, 1]
    assert [parse_choice(t, 3) for t in ["7", "2 and 3", "do it", "delete meeting"]] == [None, None, None, None]
    assert is_number_reply("7") and not is_number_reply("do it")


# --- assistant task lookup (pure, no DB) ---------------------------------------

def test_task_lookup_is_deterministic_and_never_guesses():
    from types import SimpleNamespace as T

    from app.features.assistant.service import _match_tasks
    from app.features.tasks.models import TaskStatus

    tasks = [
        T(title="Feed the cat", status=TaskStatus.PENDING),
        T(title="Meeting with client", status=TaskStatus.PENDING),
        T(title="Meeting with design team", status=TaskStatus.PENDING),
        T(title="Old cat chore", status=TaskStatus.CANCELLED),
    ]
    titles = lambda q: [t.title for t in _match_tasks(tasks, q)]  # noqa: E731
    assert titles("feeding the cat") == ["Feed the cat"]           # word form
    assert titles("the cat task") == ["Feed the cat"]              # filler words; cancelled skipped
    assert titles("meeting") == ["Meeting with client", "Meeting with design team"]  # several -> caller asks
    assert titles("meetings with the client") == ["Meeting with client"]
    assert titles("buy a spaceship") == []
    assert titles("task") == []                                    # only filler -> no match


def test_task_lookup_links_word_forms_stemming_misses():
    # Seen live: Gemini said "meditation", the task is "meditate".
    from types import SimpleNamespace as T

    from app.features.assistant.service import _match_tasks
    from app.features.tasks.models import TaskStatus

    tasks = [T(title=n, status=TaskStatus.PENDING) for n in ["meditate", "Update report", "planning session"]]
    titles = lambda q: [t.title for t in _match_tasks(tasks, q)]  # noqa: E731
    assert titles("the meditation task") == ["meditate"]
    assert titles("updating the report") == ["Update report"]
    assert titles("planting") == []  # "plant" vs "plann": first 5 letters differ


# --- Gemini quota replies (pure parsing, no network) --------------------------

import httpx as _httpx

from app.core.gemini_quota import parse_quota_error as _parse_quota


def _quota_429(quota_id, retry_delay=None):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": quota_id, "quotaValue": "20"}]}]
    if retry_delay is not None:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay})
    return _httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": details}})


def test_quota_parse_daily_limit_uses_googles_reset_time():
    # Shape copied from a real 429 (gemini-3.8-flash, 2026-11-19).
    hit = _parse_quota(_quota_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "535s"))
    assert (hit.kind, hit.seconds) == ("day", 535.0)


def test_quota_parse_minute_limit_without_delay_skips_a_minute():
    hit = _parse_quota(_quota_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
    assert (hit.kind, hit.seconds) == ("minute", 60)


def test_quota_parse_unreadable_body_never_locks_a_model_out_long():
    hit = _parse_quota(_httpx.Response(429, text="<html>rate limited</html>"))
    assert (hit.kind, hit.seconds) == ("unknown", 60)


def test_quota_parse_retired_model():
    hit = _parse_quota(_httpx.Response(404, json={"error": {"message": "no longer available"}}))
    assert hit.kind == "retired" and hit.seconds == 24 * 3600


def test_gemini_null_lists_are_accepted():
    # Seen live (gemini-3.1-flash-lite): empty lists come back as null.
    from app.features.assistant.schemas import GeminiIntentOutput

    parsed = GeminiIntentOutput.model_validate({
        "intent": "pause_task", "title": "meditation", "weekdays": None, "times": None, "missing_fields": None})
    assert (parsed.weekdays, parsed.times, parsed.missing_fields) == ([], [], [])
