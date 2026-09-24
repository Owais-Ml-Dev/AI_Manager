"""The assistant's step-by-step task creation.

These tests never call Gemini. A fake parser stands in for it.
"""

from datetime import date

import pytest

from src.modules.assistant.create_flow import apply_answer, local_intent, next_step
from src.modules.assistant.drafts import service as draft_service
from src.modules.assistant.providers.base_provider import ProviderConnectionError
from src.modules.assistant.slot_filler import (
    extract_duration,
    extract_repeat,
    parse_reminder_windows,
)


TODAY = date(2026, 9, 23)


# ---------------------------------------------------------------
# Plain-text readers
# ---------------------------------------------------------------

def test_repeat_words():
    assert extract_repeat("everyday")["type"] == "everyday"
    assert extract_repeat("Every day")["type"] == "everyday"
    assert extract_repeat("weekdays")["type"] == "weekdays"
    assert extract_repeat("weekends")["type"] == "weekends"
    assert extract_repeat("custom dates")["type"] == "custom_dates"
    assert extract_repeat("not sure") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4:22 pm", [("16:22", "16:23")]),
        ("9 am to 11 am", [("09:00", "11:00")]),
        ("9-11 am", [("09:00", "11:00")]),
        ("11 to 2 pm", [("11:00", "14:00")]),
        ("18:00 to 19:30", [("18:00", "19:30")]),
        ("09:30 - 10:00", [("09:30", "10:00")]),
        ("9am-11am and 5pm-7pm", [("09:00", "11:00"), ("17:00", "19:00")]),
    ],
)
def test_clear_times(text, expected):
    windows, ambiguous = parse_reminder_windows(text, lenient=True)
    assert not ambiguous
    assert [(w["start_time"], w["end_time"]) for w in windows] == expected


@pytest.mark.parametrize("text", ["4:22", "9 to 11", "9"])
def test_times_without_am_pm_are_not_guessed(text):
    windows, ambiguous = parse_reminder_windows(text, lenient=True)
    assert windows is None
    assert ambiguous is True


def test_am_pm_answer_resolves_time():
    windows, _ = parse_reminder_windows("4:22", lenient=True, hint="pm")
    assert windows[0]["start_time"] == "16:22"


def test_durations():
    assert extract_duration("for 7 days", TODAY) == {
        "start_date": "2026-09-23",
        "end_date": "2026-09-29",
    }
    assert extract_duration("25 sep to 5 oct", TODAY) == {
        "start_date": "2026-09-25",
        "end_date": "2026-10-05",
    }
    assert extract_duration("remind me to study tomorrow for 2 weeks", TODAY) == {
        "start_date": "2026-09-24",
        "end_date": "2026-10-07",
    }


# ---------------------------------------------------------------
# Step order
# ---------------------------------------------------------------

def _fields_in_order(action, answers):
    task, collect, asked = {"title": "Study"}, {}, []
    for answer in answers:
        step = next_step(action, task, collect)
        asked.append(step["field"])
        task, collect, understood = apply_answer(step["field"], action, task, collect, answer, TODAY)
        assert understood, (step["field"], answer)
    assert next_step(action, task, collect) is None
    return asked, task


def test_recurring_order():
    asked, task = _fields_in_order(
        "create_recurring_task",
        [
            "from today to 15 oct",
            "weekdays",
            "2",
            "9 am to 11 am",
            "2",
            "6-8 pm",
            "3",
        ],
    )

    assert asked == [
        "duration",
        "repeat",
        "reminders.count",
        "reminders.window",
        "reminders.window_reminder_count",
        "reminders.window",
        "reminders.window_reminder_count",
    ]
    assert len(task["reminders"]) == 2


def test_repeat_until_done_order():
    asked, _ = _fields_in_order(
        "create_repeat_until_done_task",
        [
            "from today to 15 oct",
            "everyday",
            "1",
            "4:22",
            "pm",
            "3",
        ],
    )

    assert asked == [
        "duration",
        "repeat",
        "reminders.count",
        "reminders.window",
        "reminders.meridiem",
        "reminders.window_reminder_count",
    ]


def test_local_title_when_gemini_is_down():
    intent = local_intent("Add buy task", TODAY)
    assert intent["action"] == "create_repeat_until_done_task"
    assert intent["arguments"]["task"]["title"] == "Buy"


# ---------------------------------------------------------------
# Full draft flow (uses the test MongoDB from conftest)
# ---------------------------------------------------------------

def _fake_parser(calls, fail=False):
    def parse(message, timezone_name="UTC", api_key=None, current_draft=None, pending_question=None):
        from src.modules.assistant.task_parser import local_now

        calls.append(message)
        if fail:
            raise ProviderConnectionError("Gemini is temporarily overloaded.")
        return {
            "provider": "gemini",
            "type": "api",
            "model": "fake",
            "timezone": timezone_name,
            "local_now": local_now(timezone_name),
            "intent": {
                "action": "create_repeat_until_done_task",
                "arguments": {"task": {"title": "Buy", "description": "Reminder to buy."}},
            },
        }

    return parse


def _run(messages):
    draft_id, result = None, None
    for message in messages:
        result = draft_service.preview_task_draft(message, "+05:30", "k", draft_id=draft_id)
        draft_id = result["draft_id"]
    return result


def test_screenshot_conversation(app, monkeypatch):
    calls = []
    monkeypatch.setattr(draft_service, "parse_task_message", _fake_parser(calls))

    with app.app_context():
        result = _run([
            "Add buy task",
            "today for 2 weeks",
            "Everyday",
            "1",
            "4:22",
        ])

        assert "AM or PM" in result["question"]

        result = _run_more(
            result,
            [
                "PM",
                "3",
            ],
        )

    assert result["status"] in {"ready", "duplicate_review"}
    task = result["command"]["arguments"]["task"]
    assert task["reminders"][0]["start_time"] == "16:22"
    assert task["description"]
    assert len(calls) == 1  # only the first message needed Gemini


def _run_more(previous, messages):
    draft_id, result = previous["draft_id"], previous
    for message in messages:
        result = draft_service.preview_task_draft(message, "+05:30", "k", draft_id=draft_id)
    return result


def test_gemini_down_still_creates(app, monkeypatch):
    calls = []
    monkeypatch.setattr(draft_service, "parse_task_message", _fake_parser(calls, fail=True))

    with app.app_context():
        result = _run([
            "Create buy",
            "today for 2 weeks",
            "weekends",
            "1",
            "7 pm to 9 pm",
            "2",
        ])

    assert result["status"] in {"ready", "duplicate_review"}
    assert result["command"]["arguments"]["task"]["title"] == "Buy"
