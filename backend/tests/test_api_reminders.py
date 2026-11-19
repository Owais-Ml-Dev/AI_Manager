"""API + service tests for reminders, recurring occurrences, and the reminder
worker's generation/sweep logic. Real DB. Includes regression tests for:
  bug 1 — changing a schedule must clear future deliveries/occurrences,
  bug 2 — a past start_date must not create (and burst-send) stale reminders,
  bug 4 — concurrent occurrence syncs must not 500 or duplicate rows.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.database import AsyncSessionLocal
from app.features.reminders import repository as reminders_repository
from app.features.reminders import service as reminders_service

pytestmark = pytest.mark.usefixtures("clean_accounts")

TODAY = date.today()
PAST = (TODAY - timedelta(days=3)).isoformat()


async def set_config(client, headers, task_id, **body):
    body.setdefault("start_date", PAST)
    body.setdefault("day_selection_type", "every_day")
    return await client.put(f"/tasks/{task_id}/reminder-config", json=body, headers=headers)


async def add_time(client, headers, task_id, hhmmss):
    response = await client.post(
        f"/tasks/{task_id}/reminder-config/reminder-times", json={"time_of_day": hhmmss}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def deliveries(client, headers, task_id):
    return (await client.get(f"/tasks/{task_id}/reminder-config/deliveries", headers=headers)).json()


async def occurrences(client, headers, task_id):
    return (await client.get(f"/tasks/{task_id}/occurrences", headers=headers)).json()


# --- reminder config & times -------------------------------------------------

async def test_one_time_config_requires_end_date(client, auth_a, make_task):
    task = await make_task("one-time")
    assert (await set_config(client, auth_a, task["id"])).status_code == 400
    ok = await set_config(client, auth_a, task["id"], end_date=TODAY.isoformat())
    assert ok.status_code == 200


async def test_recurring_config_can_be_open_ended(client, auth_a, make_task):
    task = await make_task("gym", category="recurring")
    response = await set_config(client, auth_a, task["id"])
    assert response.status_code == 200
    assert response.json()["end_date"] is None


async def test_reminder_times_crud(client, auth_a, make_task):
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"])
    base = f"/tasks/{task['id']}/reminder-config/reminder-times"

    first = await add_time(client, auth_a, task["id"], "07:00:00")
    await add_time(client, auth_a, task["id"], "07:30:00")
    dup = await client.post(base, json={"time_of_day": "07:00:00"}, headers=auth_a)
    assert dup.status_code == 400

    moved = await client.patch(f"{base}/{first['id']}", json={"time_of_day": "06:45:00"}, headers=auth_a)
    assert moved.json()["time_of_day"] == "06:45:00"
    assert (await client.delete(f"{base}/{first['id']}", headers=auth_a)).status_code == 204
    assert [t["time_of_day"] for t in (await client.get(base, headers=auth_a)).json()] == ["07:30:00"]


# --- occurrences ---------------------------------------------------------------

async def test_occurrences_generated_with_past_days_missed(client, auth_a, make_task):
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"])
    by_date = {o["occurrence_date"]: o["status"] for o in await occurrences(client, auth_a, task["id"])}
    assert sum(1 for s in by_date.values() if s == "missed") == 3
    assert by_date[TODAY.isoformat()] == "pending"


async def test_completing_occurrence_does_not_complete_task(client, auth_a, make_task):
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"])
    today = next(o for o in await occurrences(client, auth_a, task["id"]) if o["occurrence_date"] == TODAY.isoformat())
    url = f"/tasks/{task['id']}/occurrences/{today['id']}"

    assert (await client.patch(url, json={"status": "completed"}, headers=auth_a)).json()["status"] == "completed"
    assert (await client.get(f"/tasks/{task['id']}", headers=auth_a)).json()["status"] == "pending"
    # Resolved occurrences are locked.
    assert (await client.patch(url, json={"status": "skipped"}, headers=auth_a)).status_code == 400


async def test_occurrences_rejected_for_one_time_tasks(client, auth_a, make_task):
    task = await make_task("one-time")
    await set_config(client, auth_a, task["id"], end_date=TODAY.isoformat())
    assert (await client.get(f"/tasks/{task['id']}/occurrences", headers=auth_a)).status_code == 400


async def test_schedule_change_replaces_future_occurrences_keeps_history(client, auth_a, make_task):
    # Regression for bug 1 (occurrence side).
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"])
    await occurrences(client, auth_a, task["id"])  # generate under every_day

    await set_config(client, auth_a, task["id"], day_selection_type="weekends")
    after = await occurrences(client, auth_a, task["id"])

    pending_weekdays = [
        o for o in after
        if o["status"] == "pending" and date.fromisoformat(o["occurrence_date"]).isoweekday() <= 5
    ]
    assert pending_weekdays == []
    assert any(o["status"] == "pending" for o in after)  # weekend ones regenerated
    assert sum(1 for o in after if o["status"] == "missed") == 3  # history kept


async def test_concurrent_syncs_do_not_500_or_duplicate(client, auth_a, make_task):
    # Regression for bug 4.
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"], start_date=TODAY.isoformat())
    responses = await asyncio.gather(
        *[client.get(f"/tasks/{task['id']}/occurrences", headers=auth_a) for _ in range(4)],
        *[client.get("/dashboard", headers=auth_a) for _ in range(4)],
    )
    assert [r.status_code for r in responses] == [200] * 8
    dates = [o["occurrence_date"] for o in await occurrences(client, auth_a, task["id"])]
    assert len(dates) == len(set(dates))


# --- reminder worker: generation + sweep ---------------------------------------

async def _generate(db, task_id):
    # Sessions use expire_on_commit=False, so drop cached rows the API may
    # have changed since this session last loaded them.
    db.expire_all()
    config = await reminders_repository.get_by_task_id(db, task_id)
    await reminders_service._generate_deliveries_for_task(db, task_id, config)


async def test_generation_skips_slots_already_in_the_past(client, auth_a, make_task, db):
    # Regression for bug 2: start_date 3 days ago used to queue 3 days of
    # already-due reminders, which the next sweep sent all at once.
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"])
    await add_time(client, auth_a, task["id"], "00:00:01")
    await add_time(client, auth_a, task["id"], "23:59:59")
    await _generate(db, task["id"])

    generated = await deliveries(client, auth_a, task["id"])
    now = datetime.now(timezone.utc)
    assert generated, "future slots should still be generated"
    assert all(datetime.fromisoformat(d["scheduled_for"]) > now for d in generated)


def weekdays_of(rows, status="scheduled"):
    return {datetime.fromisoformat(d["scheduled_for"]).isoweekday() for d in rows if d["status"] == status}


async def test_schedule_change_replaces_future_deliveries(client, auth_a, make_task):
    # Regression for bug 1 (delivery side). Deliveries now regenerate
    # immediately on a config change, not on the worker's next pass.
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"], start_date=TODAY.isoformat())
    await add_time(client, auth_a, task["id"], "23:59:59")
    assert weekdays_of(await deliveries(client, auth_a, task["id"])) & {1, 2, 3, 4, 5}

    await set_config(client, auth_a, task["id"], start_date=TODAY.isoformat(), day_selection_type="weekends")
    assert weekdays_of(await deliveries(client, auth_a, task["id"])) == {6, 7}


async def test_changing_reminder_time_moves_future_deliveries(client, auth_a, make_task):
    task = await make_task("gym", category="recurring")
    await set_config(client, auth_a, task["id"], start_date=TODAY.isoformat())
    slot = await add_time(client, auth_a, task["id"], "23:59:58")

    url = f"/tasks/{task['id']}/reminder-config/reminder-times/{slot['id']}"
    await client.patch(url, json={"time_of_day": "23:59:57"}, headers=auth_a)

    times = {
        datetime.fromisoformat(d["scheduled_for"]).time().isoformat()
        for d in await deliveries(client, auth_a, task["id"])
        if d["status"] == "scheduled"
    }
    assert times == {"23:59:57"}  # nothing left firing at the old time


async def _due_delivery(client, auth_a, make_task, db, title, minutes_ago):
    """A one-time task with a single delivery already `minutes_ago` overdue
    (inserted directly — generation never creates past slots)."""
    task = await make_task(title)
    await set_config(client, auth_a, task["id"], start_date=TODAY.isoformat(), end_date=TODAY.isoformat())
    time_id = (await add_time(client, auth_a, task["id"], "00:00:00"))["id"]
    due = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    await reminders_repository.bulk_create_deliveries(db, [(task["id"], time_id, due)])
    await db.commit()  # repositories only stage; other sessions must see it
    return task, due


def status_at(rows, when):
    return next(d["status"] for d in rows if datetime.fromisoformat(d["scheduled_for"]) == when)


async def test_sweep_sends_due_and_cancels_completed(client, auth_a, make_task, db):
    open_task, open_due = await _due_delivery(client, auth_a, make_task, db, "still open", 1)
    done_task, done_due = await _due_delivery(client, auth_a, make_task, db, "already done", 1)
    await client.patch(f"/tasks/{done_task['id']}", json={"status": "completed"}, headers=auth_a)

    db.expire_all()
    await reminders_service.run_reminder_sweep(db)

    assert status_at(await deliveries(client, auth_a, open_task["id"]), open_due) == "sent"
    assert status_at(await deliveries(client, auth_a, done_task["id"]), done_due) == "cancelled"


async def test_stale_delivery_is_cancelled_not_sent(client, auth_a, make_task, db):
    task, due = await _due_delivery(client, auth_a, make_task, db, "server was down", 120)
    db.expire_all()
    await reminders_service.run_reminder_sweep(db)
    assert status_at(await deliveries(client, auth_a, task["id"]), due) == "cancelled"


async def test_concurrent_sweeps_send_each_reminder_once(client, auth_a, make_task, db, monkeypatch):
    task, _ = await _due_delivery(client, auth_a, make_task, db, "send me once", 1)
    sent = []
    monkeypatch.setattr(
        reminders_service, "send_reminder_notification", lambda task_id, *_: sent.append(task_id)
    )

    async def sweep():
        async with AsyncSessionLocal() as session:
            await reminders_service.run_reminder_sweep(session)

    await asyncio.gather(sweep(), sweep(), sweep())
    assert sent.count(task["id"]) == 1
