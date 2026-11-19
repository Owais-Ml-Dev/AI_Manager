"""Tests for the assistant's conversation state machine. Gemini is replaced
by a scripted fake (only the NLU call — Redis state, confirmation logic and
real DB writes all run for real). The fake fails loudly if called when no
answer was scripted, which proves "yes"/"no"/number replies are handled by
plain rules without any Gemini call. Includes regressions for bug 5.
"""
import pytest

from app.core.gemini import GeminiError, GeminiUnavailableError
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
