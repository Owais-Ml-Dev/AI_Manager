"""Tests for the assistant's conversation state machine. Gemini is replaced
by a scripted fake (only the NLU call — Redis state, confirmation logic and
real DB writes all run for real). The fake fails loudly if called when no
answer was scripted, which proves "yes"/"no"/number replies are handled by
plain rules without any Gemini call. Includes regressions for bug 5.
"""
import pytest

from app.core.gemini import GeminiError
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
