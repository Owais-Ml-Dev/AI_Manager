"""Tests for the assistant's conversation state machine. Gemini is replaced
by a scripted fake (only the NLU call — Redis state, confirmation logic and
real DB writes all run for real). The fake fails loudly if called when no
answer was scripted, which proves "yes"/"no"/number replies are handled by
plain rules without any Gemini call. Includes regressions for bug 5.
"""
import pytest

from datetime import datetime, timedelta, timezone

from app.core.gemini import GeminiError, GeminiQuotaExhaustedError, GeminiUnavailableError
from app.features.assistant import service as assistant_service

pytestmark = pytest.mark.usefixtures("clean_accounts")


@pytest.fixture
def gemini(monkeypatch):
    """Queue of scripted Gemini outputs; append a dict (or an Exception)."""
    queue = []

    async def fake_generate_json(prompt):
        if not queue:
            raise AssertionError("Gemini was called but no response was scripted")
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(assistant_service, "generate_json", fake_generate_json)
    return queue


@pytest.fixture
def say(client, auth_a):
    async def _say(message):
        response = await client.post("/assistant/message", json={"message": message}, headers=auth_a)
        assert response.status_code == 200, response.text
        return response.json()

    return _say


async def titles(client, headers):
    return sorted(t["title"] for t in (await client.get("/tasks", headers=headers)).json())


async def test_create_confirm_yes_creates_task(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Buy milk"})
    first = await say("Create a task called Buy milk")
    assert first["state"] == "awaiting_confirmation"
    assert await titles(client, auth_a) == []  # nothing written before confirmation

    second = await say("yes")  # no scripted response: must not reach Gemini
    assert second["state"] == "idle"
    assert await titles(client, auth_a) == ["Buy milk"]


async def test_create_confirm_no_cancels(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Buy milk"})
    await say("Create a task called Buy milk")
    assert (await say("no"))["reply"] == "Cancelled."
    assert await titles(client, auth_a) == []


async def test_missing_title_is_collected_on_next_turn(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": None, "missing_fields": ["title"]})
    gemini.append({"intent": "create_task", "title": "Water the plants"})
    assert (await say("Create a task"))["state"] == "collecting_information"
    reply = await say("Call it Water the plants")
    assert reply["state"] == "awaiting_confirmation"
    assert "Water the plants" in reply["reply"]


async def test_modified_request_invalidates_pending_confirmation(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Buy milk"})
    gemini.append({"intent": "retrieve_tasks"})
    await say("Create a task called Buy milk")
    reply = await say("actually, show my tasks")
    assert reply["state"] == "idle"
    assert await titles(client, auth_a) == []  # the stale create was NOT executed


async def test_ambiguous_title_selection_confirms_real_name(client, auth_a, gemini, say, make_task):
    # Regression for bug 5a: confirmation used to echo the search text ("meeting").
    await make_task("Meeting with Bob")
    await make_task("Meeting with Alice")
    gemini.append({"intent": "delete_task", "title": "meeting"})

    pick = await say("Delete meeting")
    assert pick["state"] == "awaiting_task_selection"
    chosen = pick["reply"].splitlines()[2].split(") ", 1)[1]  # option 2's title

    confirm = await say("2")
    assert f'"{chosen}"' in confirm["reply"]
    await say("yes")
    remaining = await titles(client, auth_a)
    assert chosen not in remaining and len(remaining) == 1


async def test_selection_can_be_cancelled_or_replaced(client, auth_a, gemini, say, make_task):
    # Regression: during task selection, anything but a pick used to re-ask
    # forever ("I'm not sure which one you mean"), trapping the user.
    await make_task("Meeting with Bob")
    await make_task("Meeting with Alice")
    await make_task("Dentist")

    gemini.append({"intent": "delete_task", "title": "meeting"})
    await say("Delete meeting")
    cancelled = await say("no")  # rule-based: no Gemini call
    assert cancelled == {"reply": "Cancelled.", "state": "idle"}

    gemini.append({"intent": "delete_task", "title": "meeting"})
    await say("Delete meeting")
    assert (await say("7"))["state"] == "awaiting_task_selection"  # out-of-range number re-asks
    gemini.append({"intent": "delete_task", "title": "Dentist"})
    switched = await say("actually, delete Dentist instead")  # treated as a new request
    assert switched["state"] == "awaiting_confirmation"
    assert '"Dentist"' in switched["reply"]
    await say("yes")
    assert await titles(client, auth_a) == ["Meeting with Alice", "Meeting with Bob"]


async def test_create_warns_when_title_already_exists(client, auth_a, gemini, say, make_task):
    # Guard for Gemini misreading "make X urgent" as create_task.
    await make_task("Water the plants")
    gemini.append({"intent": "create_task", "title": "Water the plants", "urgent": True})
    reply = await say("Make Water the plants urgent")
    assert reply["state"] == "awaiting_confirmation"
    assert "already have a task" in reply["reply"]


async def test_task_deleted_before_yes_gives_message_not_500(client, auth_a, gemini, say, make_task):
    # Regression for bug 5b.
    task = await make_task("Dentist")
    gemini.append({"intent": "delete_task", "title": "Dentist"})
    await say("Delete Dentist")
    await client.delete(f"/tasks/{task['id']}", headers=auth_a)
    reply = await say("yes")  # `say` asserts HTTP 200
    assert reply["reply"].startswith("Couldn't do that")
    assert reply["state"] == "idle"


async def test_retrieve_tasks_is_read_only_and_immediate(client, auth_a, gemini, say, make_task):
    await make_task("Buy milk")
    gemini.append({"intent": "retrieve_tasks"})
    reply = await say("Show my pending tasks")
    assert reply["state"] == "idle"
    assert "Buy milk" in reply["reply"]


async def test_gemini_failure_degrades_gracefully(gemini, say):
    gemini.append(GeminiError("503 overloaded"))
    reply = await say("Create a task called X")
    assert reply["state"] == "idle"
    assert "didn't understand" in reply["reply"]


async def test_intent_outside_allowlist_is_rejected(client, auth_a, gemini, say):
    gemini.append({"intent": "drop_all_tables", "title": "x"})
    reply = await say("do something weird")
    assert reply["state"] == "idle"
    assert await titles(client, auth_a) == []


async def test_other_user_has_separate_conversation(client, auth_b, gemini, say):
    gemini.append({"intent": "create_task", "title": "A's task"})
    await say("Create a task called A's task")  # user A now awaiting confirmation
    gemini.append({"intent": "unknown"})
    response = await client.post("/assistant/message", json={"message": "yes"}, headers=auth_b)
    assert response.json()["state"] == "idle"  # B's "yes" didn't confirm A's action
    assert await titles(client, auth_b) == []


async def test_lookup_matches_word_forms_and_filler_words(client, auth_a, gemini, say, make_task):
    # Found by the reworded live run: "feeding the cat" didn't find "Feed the cat".
    await make_task("Feed the cat")
    await make_task("Renew passport")
    gemini.append({"intent": "complete_task", "title": "feeding the cat"})
    reply = await say("I finished feeding the cat")
    assert reply["state"] == "awaiting_confirmation"
    assert '"Feed the cat"' in reply["reply"]
    await say("no")

    gemini.append({"intent": "delete_task", "title": "passport wala task"})
    reply = await say("passport wala task delete kar do")
    assert '"Renew passport"' in reply["reply"]


async def test_gemini_unavailable_says_busy_and_keeps_request(gemini, say):
    gemini.append({"intent": "create_task", "title": None, "missing_fields": ["title"]})
    assert (await say("Create a task"))["state"] == "collecting_information"
    gemini.append(GeminiUnavailableError("ReadTimeout"))
    reply = await say("the title should be Feed the cat")
    assert "busy" in reply["reply"]
    assert reply["state"] == "collecting_information"  # retry can continue


async def test_cancel_handled_by_rules_without_gemini(gemini, say):
    # No scripted Gemini answers: any Gemini call would fail this test.
    assert (await say("cancel")) == {"reply": "Nothing to cancel.", "state": "idle"}
    gemini.append({"intent": "create_task", "title": None, "missing_fields": ["title"]})
    await say("Create a task")
    assert (await say("never mind")) == {"reply": "Cancelled.", "state": "idle"}


async def test_all_models_out_of_quota_says_when_it_comes_back(gemini, say):
    gemini.append(GeminiQuotaExhaustedError(datetime.now(timezone.utc) + timedelta(minutes=40)))
    reply = await say("Show my tasks")
    assert "usage limit" in reply["reply"] and "40 minutes" in reply["reply"]
    assert reply["state"] == "idle"


# --- Step 4: recurring tasks, reminders, pause/resume, voice ---------------------

from datetime import timedelta  # noqa: E402

from app.core.timezones import today_in, zone  # noqa: E402

TODAY = today_in(zone("Asia/Kolkata"))  # test users use the default zone


async def schedule_of(client, headers, task_id):
    config = (await client.get(f"/tasks/{task_id}/reminder-config", headers=headers)).json()
    times = [t["time_of_day"] for t in (await client.get(
        f"/tasks/{task_id}/reminder-config/reminder-times", headers=headers)).json()]
    return config, times


async def test_recurring_task_created_with_its_schedule(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Swim", "category": "recurring",
                   "day_selection": "custom_weekdays", "weekdays": [5, 1, 3], "times": ["07:00"]})
    first = await say("swim every monday wednesday and friday at 7am")
    assert first["state"] == "awaiting_confirmation"
    assert first["reply"] == 'Create recurring task "Swim": every Mon, Wed and Fri at 07:00, starting today. Confirm?'
    assert await titles(client, auth_a) == []  # nothing before confirmation

    done = await say("yes please")  # voice-style yes, no Gemini call
    assert done["state"] == "idle" and done["reply"].startswith('Created recurring task "Swim"')
    task = (await client.get("/tasks", headers=auth_a)).json()[0]
    assert task["category"] == "recurring"
    config, times = await schedule_of(client, auth_a, task["id"])
    assert (config["day_selection_type"], config["custom_weekdays"], config["start_date"]) == (
        "custom_weekdays", [1, 3, 5], TODAY.isoformat())
    assert times == ["07:00:00"]
    assert (await client.get(f"/tasks/{task['id']}/occurrences", headers=auth_a)).json()  # generated
    deliveries = (await client.get(f"/tasks/{task['id']}/reminder-config/deliveries", headers=auth_a)).json()
    assert deliveries and all(d["scheduled_for"].endswith("07:00:00+05:30") for d in deliveries)


async def test_recurring_asks_which_days(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Stretch", "category": "recurring"})
    asked = await say("add a recurring task to stretch")
    assert asked["state"] == "collecting_information" and asked["reply"].startswith("Which days")
    gemini.append({"intent": "create_task", "day_selection": "weekdays"})
    confirm = await say("weekdays")
    assert confirm["reply"] == 'Create recurring task "Stretch": on weekdays (no reminder time), starting today. Confirm?'
    await say("haan")
    task = (await client.get("/tasks", headers=auth_a)).json()[0]
    config, times = await schedule_of(client, auth_a, task["id"])
    assert (task["title"], config["day_selection_type"], times) == ("Stretch", "weekdays", [])


async def test_reminder_for_existing_one_time_task_runs_until_due(client, auth_a, gemini, say, make_task):
    due = (TODAY + timedelta(days=5)).isoformat()
    task = await make_task("Pay bills", due_date=due)
    gemini.append({"intent": "configure_reminder", "title": "pay bills", "times": ["09:00"]})
    confirm = await say("remind me about pay bills at 9")
    assert confirm["reply"] == (f'Set reminders for "Pay bills": every day at 09:00, starting today until {due}. '
                                "This replaces its current reminder schedule. Confirm?")
    await say("ok")
    config, times = await schedule_of(client, auth_a, task["id"])
    assert (config["start_date"], config["end_date"], times) == (TODAY.isoformat(), due, ["09:00:00"])


async def test_reminder_for_task_without_due_date_asks_until_when(client, auth_a, gemini, say, make_task):
    task = await make_task("Read book")
    gemini.append({"intent": "configure_reminder", "title": "read book", "day_selection": "weekends", "times": ["20:00"]})
    asked = await say("remind me about read book on weekends at 8pm")
    assert asked["reply"] == "Until which date should the reminders run?"
    end = (TODAY + timedelta(days=30)).isoformat()
    gemini.append({"intent": "configure_reminder", "end_date": end})
    await say("for a month")
    await say("yes")
    config, times = await schedule_of(client, auth_a, task["id"])
    assert (config["day_selection_type"], config["end_date"], times) == ("weekends", end, ["20:00:00"])


async def test_pause_and_resume_asks_for_new_due_date(client, auth_a, gemini, say, make_task):
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    task = await make_task("Passport", due_date=yesterday)
    gemini.append({"intent": "pause_task", "title": "passport"})
    assert (await say("put passport on hold"))["reply"].startswith('Pause "Passport"')
    await say("yes")
    assert (await client.get(f"/tasks/{task['id']}", headers=auth_a)).json()["status"] == "paused"

    gemini.append({"intent": "resume_task", "title": "passport"})
    await say("resume passport")
    asked = await say("yes")  # due date passed while paused -> ask, don't fail
    assert asked["state"] == "collecting_information"
    assert asked["reply"] == "The due date passed while it was paused. What's the new due date?"
    new_due = (TODAY + timedelta(days=7)).isoformat()
    gemini.append({"intent": "resume_task", "due_date": new_due})
    confirm = await say("next week")
    assert confirm["reply"] == f'Resume "Passport" with new due date {new_due}. Confirm?'
    await say("yes")
    resumed = (await client.get(f"/tasks/{task['id']}", headers=auth_a)).json()
    assert (resumed["status"], resumed["due_date"]) == ("pending", new_due)


async def test_voice_input_uses_the_same_path(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Buy milk"})
    await client.post("/assistant/message", headers=auth_a, json={"message": "buy milk", "input": "voice"})
    spoken_yes = await client.post("/assistant/message", headers=auth_a, json={"message": "Yes.", "input": "voice"})
    assert spoken_yes.json()["state"] == "idle"
    assert await titles(client, auth_a) == ["Buy milk"]
    bad = await client.post("/assistant/message", headers=auth_a, json={"message": "x", "input": "telepathy"})
    assert bad.status_code == 422


async def test_yes_with_a_change_is_not_a_confirmation(client, auth_a, gemini, say):
    gemini.append({"intent": "create_task", "title": "Buy milk"})
    await say("create buy milk")
    gemini.append({"intent": "create_task", "title": "Buy bread"})  # must be asked again
    changed = await say("yes but call it buy bread")
    assert changed["reply"].startswith('Create a one-time task "Buy bread"')
    assert await titles(client, auth_a) == []  # the stale "Buy milk" was NOT created


async def test_spoken_choice_picks_a_task(client, auth_a, gemini, say, make_task):
    await make_task("Meeting with Bob")
    await make_task("Meeting with Alice")
    gemini.append({"intent": "delete_task", "title": "meeting"})
    pick = await say("delete meeting")
    second = pick["reply"].splitlines()[2].split(") ", 1)[1]
    confirm = await say("the second one")
    assert confirm["reply"] == f'Delete "{second}". Confirm?'


def _fail_when_saving_times(monkeypatch):
    """Makes the reminder-time write fail — i.e. AFTER the schedule itself
    has already been staged in the same transaction."""
    from app.common.exceptions import ValidationError as DomainValidationError
    from app.features.reminders import repository as reminders_repository

    async def broken(*args, **kwargs):
        raise DomainValidationError("reminder time store unavailable")

    monkeypatch.setattr(reminders_repository, "create_time", broken)


async def test_failed_schedule_leaves_no_half_created_task(client, auth_a, gemini, say, monkeypatch):
    _fail_when_saving_times(monkeypatch)
    gemini.append({"intent": "create_task", "title": "Yoga", "category": "recurring",
                   "day_selection": "every_day", "times": ["06:00"]})
    await say("yoga every day at 6")
    result = await say("yes")
    assert result["reply"].startswith("Couldn't do that")
    assert await titles(client, auth_a) == []  # task and schedule rolled back together


async def test_failed_reminder_update_changes_nothing(client, auth_a, gemini, say, make_task, monkeypatch):
    """Regression: updating an existing task's reminders saved the schedule
    and the times separately, so a failure could leave a new schedule with
    the old times. Now it's one transaction."""
    due = (TODAY + timedelta(days=10)).isoformat()
    task = await make_task("Pay bills", due_date=due)
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=auth_a, json={
        "start_date": TODAY.isoformat(), "end_date": due, "day_selection_type": "every_day"})
    await client.post(f"{base}/reminder-times", headers=auth_a, json={"time_of_day": "09:00:00"})
    before_config, before_times = await schedule_of(client, auth_a, task["id"])
    before_deliveries = (await client.get(f"{base}/deliveries", headers=auth_a)).json()
    before_history = (await client.get(f"/tasks/{task['id']}/history", headers=auth_a)).json()

    _fail_when_saving_times(monkeypatch)
    gemini.append({"intent": "configure_reminder", "title": "pay bills",
                   "day_selection": "weekends", "times": ["07:00"]})
    await say("remind me about pay bills on weekends at 7am")
    result = await say("yes")
    assert result["reply"].startswith("Couldn't do that")

    # Everything exactly as before: schedule, times, planned reminders, history.
    assert await schedule_of(client, auth_a, task["id"]) == (before_config, before_times)
    assert before_config["day_selection_type"] == "every_day" and before_times == ["09:00:00"]
    assert (await client.get(f"{base}/deliveries", headers=auth_a)).json() == before_deliveries
    assert (await client.get(f"/tasks/{task['id']}/history", headers=auth_a)).json() == before_history


async def test_reminder_update_replaces_times_in_one_go(client, auth_a, gemini, say, make_task):
    due = (TODAY + timedelta(days=10)).isoformat()
    task = await make_task("Pay bills", due_date=due)
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=auth_a, json={
        "start_date": TODAY.isoformat(), "end_date": due, "day_selection_type": "every_day"})
    for t in ("09:00:00", "18:00:00"):
        await client.post(f"{base}/reminder-times", headers=auth_a, json={"time_of_day": t})

    gemini.append({"intent": "configure_reminder", "title": "pay bills", "times": ["07:00", "18:00"]})
    await say("remind me about pay bills at 7am and 6pm")
    await say("yes")
    _, times = await schedule_of(client, auth_a, task["id"])
    assert times == ["07:00:00", "18:00:00"]  # 09:00 removed, 18:00 kept, 07:00 added
    planned = {d["scheduled_for"][11:19] for d in (await client.get(f"{base}/deliveries", headers=auth_a)).json()
               if d["status"] == "scheduled"}
    assert planned <= {"07:00:00", "18:00:00"} and "09:00:00" not in planned


async def test_reminder_for_unknown_task_offers_to_create_it(client, auth_a, gemini, say):
    # Seen live: "Remind me to submit the tax form by Friday at 5pm" read as a
    # reminder on an existing task. None exists -> offer to create it.
    due = (TODAY + timedelta(days=2)).isoformat()
    gemini.append({"intent": "configure_reminder", "title": "submit the tax form",
                   "due_date": due, "due_time": "17:00", "times": ["17:00"]})
    offer = await say("remind me to submit the tax form at 5pm")
    assert offer["state"] == "awaiting_confirmation"
    assert offer["reply"].startswith('There\'s no task called "submit the tax form" yet, so I\'ll create it. '
                                     f'Create a one-time task "submit the tax form", due {due} at 17:00')
    assert await titles(client, auth_a) == []  # still nothing before yes
    await say("yes")
    task = (await client.get("/tasks", headers=auth_a)).json()[0]
    assert (task["category"], task["due_date"], task["due_time"]) == ("one_time", due, "17:00:00")
    config, times = await schedule_of(client, auth_a, task["id"])
    assert (config["end_date"], times) == (due, ["17:00:00"])
