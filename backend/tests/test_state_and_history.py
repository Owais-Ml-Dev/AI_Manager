"""Step 3: reads never write; time-driven changes (overdue, missed, paused
days skipped) come from the worker's maintenance step and are recorded in
history automatically; pause/resume; writes are atomic with their history.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text

from app.core.database import AsyncSessionLocal, engine
from app.core.timezones import today_in, zone
from app.features.history import service as history_service
from app.features.reminders import repository as reminders_repository
from app.features.reminders import service as reminders_service

pytestmark = pytest.mark.usefixtures("clean_accounts")

TODAY = today_in(zone("Asia/Kolkata"))  # test users have the default zone
YESTERDAY = TODAY - timedelta(days=1)


async def history(client, headers, task_id):
    return (await client.get(f"/tasks/{task_id}/history", headers=headers)).json()


async def sql(statement, **params):
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(statement), params)
        await session.commit()
        return result


async def recurring_with_schedule(client, headers, make_task, start, times=("23:59:59",)):
    task = await make_task("gym", category="recurring")
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=headers, json={"start_date": start.isoformat(), "day_selection_type": "every_day"})
    for t in times:
        await client.post(f"{base}/reminder-times", headers=headers, json={"time_of_day": t})
    return task


# --- reads never write ---------------------------------------------------------------

async def test_get_endpoints_never_write(client, auth_a, make_task, run_maintenance):
    late = await make_task("late", due_date=YESTERDAY.isoformat())   # overdue-eligible, not yet marked
    gym = await recurring_with_schedule(client, auth_a, make_task, YESTERDAY)
    # Simulate a day that ended since the worker last ran: yesterday back to pending.
    await sql("update occurrences set status='PENDING' where task_id=:t and occurrence_date=:d",
              t=gym["id"], d=YESTERDAY)

    writes = []

    def spy(conn, cursor, statement, *args):
        verb = statement.lstrip().split()[0].upper()
        if verb in ("INSERT", "UPDATE", "DELETE", "WITH"):
            writes.append(statement.split("\n")[0][:80])

    event.listen(engine.sync_engine, "before_cursor_execute", spy)
    try:
        g = gym["id"]
        for url in ["/tasks", f"/tasks/{late['id']}", "/tasks/matrix", "/dashboard",
                    f"/tasks/{g}/analytics", f"/tasks/{late['id']}/analytics",
                    "/calendar?view=daily", "/calendar?view=weekly", "/calendar?view=monthly",
                    "/reports/monthly", f"/tasks/{g}/occurrences", f"/tasks/{g}/history",
                    f"/tasks/{g}/reminder-config", f"/tasks/{g}/reminder-config/reminder-times",
                    f"/tasks/{g}/reminder-config/deliveries", "/me/settings", "/health"]:
            assert (await client.get(url, headers=auth_a)).status_code == 200, url
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", spy)
    assert writes == []

    # ...and the worker step is what changes them, with history.
    await run_maintenance()
    assert (await client.get(f"/tasks/{late['id']}", headers=auth_a)).json()["status"] == "overdue"
    occ = {o["occurrence_date"]: o["status"] for o in (await client.get(f"/tasks/{g}/occurrences", headers=auth_a)).json()}
    assert occ[YESTERDAY.isoformat()] == "missed"


# --- automatic history ---------------------------------------------------------------

async def test_overdue_and_missed_are_recorded_once(client, auth_a, make_task, run_maintenance):
    late = await make_task("late", due_date=YESTERDAY.isoformat())
    gym = await recurring_with_schedule(client, auth_a, make_task, YESTERDAY - timedelta(days=1))

    await run_maintenance()
    await run_maintenance()  # a second pass (or a second server process) records nothing new

    late_events = [e for e in await history(client, auth_a, late["id"]) if e["event_type"] == "became_overdue"]
    assert len(late_events) == 1
    assert (late_events[0]["old_value"], late_events[0]["new_value"]) == ("pending", "overdue")

    missed = [e for e in await history(client, auth_a, gym["id"]) if e["event_type"] == "occurrence_missed"]
    # the 2 past days were marked missed when the schedule was saved — once each
    assert sorted(e["old_value"] for e in missed) == [
        (YESTERDAY - timedelta(days=1)).isoformat(), YESTERDAY.isoformat()]


async def test_change_and_history_are_saved_together(client, auth_a, make_task, monkeypatch):
    task = await make_task("original")

    async def boom(*args, **kwargs):
        raise RuntimeError("history write failed")

    monkeypatch.setattr(history_service, "record_field_update", boom)
    with pytest.raises(RuntimeError):
        await client.patch(f"/tasks/{task['id']}", headers=auth_a, json={"title": "renamed"})
    monkeypatch.undo()

    # Neither the change nor any history from it was saved.
    assert (await client.get(f"/tasks/{task['id']}", headers=auth_a)).json()["title"] == "original"
    assert [e["event_type"] for e in await history(client, auth_a, task["id"])] == ["created"]


# --- pause / resume -------------------------------------------------------------------

async def test_paused_one_time_task_never_goes_overdue(client, auth_a, make_task, run_maintenance):
    task = await make_task("passport", due_date=YESTERDAY.isoformat())
    paused = await client.post(f"/tasks/{task['id']}/pause", headers=auth_a)
    assert paused.json()["status"] == "paused"
    await run_maintenance()
    assert (await client.get(f"/tasks/{task['id']}", headers=auth_a)).json()["status"] == "paused"
    events = [e["event_type"] for e in await history(client, auth_a, task["id"])]
    assert events == ["created", "paused"]


async def test_resume_asks_for_new_due_date_when_it_passed(client, auth_a, make_task):
    task = await make_task("passport", due_date=YESTERDAY.isoformat())
    await client.post(f"/tasks/{task['id']}/pause", headers=auth_a)
    url = f"/tasks/{task['id']}/resume"

    no_date = await client.post(url, headers=auth_a)
    assert no_date.status_code == 409
    assert no_date.json()["detail"]["code"] == "new_due_date_required"

    past = await client.post(url, headers=auth_a, json={"due_date": YESTERDAY.isoformat()})
    assert past.status_code == 400

    new_due = (TODAY + timedelta(days=3)).isoformat()
    ok = await client.post(url, headers=auth_a, json={"due_date": new_due})
    assert ok.status_code == 200
    assert (ok.json()["status"], ok.json()["due_date"]) == ("pending", new_due)
    events = [(e["event_type"], e["field_name"]) for e in await history(client, auth_a, task["id"])]
    assert events == [("created", None), ("paused", "status"), ("field_updated", "due_date"), ("resumed", "status")]


async def test_resume_without_body_when_due_date_still_ahead(client, auth_a, make_task):
    task = await make_task("later", due_date=(TODAY + timedelta(days=5)).isoformat())
    await client.post(f"/tasks/{task['id']}/pause", headers=auth_a)
    resumed = await client.post(f"/tasks/{task['id']}/resume", headers=auth_a)
    assert resumed.status_code == 200 and resumed.json()["status"] == "pending"


async def test_paused_recurring_days_are_skipped_and_reminders_stop(client, auth_a, make_task, run_maintenance):
    gym = await recurring_with_schedule(client, auth_a, make_task, YESTERDAY)
    base = f"/tasks/{gym['id']}/reminder-config/deliveries"
    scheduled = lambda rows: [d for d in rows if d["status"] == "scheduled"]  # noqa: E731
    assert scheduled((await client.get(base, headers=auth_a)).json())

    await client.post(f"/tasks/{gym['id']}/pause", headers=auth_a)
    assert scheduled((await client.get(base, headers=auth_a)).json()) == []  # reminders stop

    # A day ends while paused (simulated: yesterday back to pending).
    await sql("update occurrences set status='PENDING' where task_id=:t and occurrence_date=:d",
              t=gym["id"], d=YESTERDAY)
    before = [e for e in await history(client, auth_a, gym["id"]) if e["event_type"] == "occurrence_missed"]
    await run_maintenance()
    occ = {o["occurrence_date"]: o["status"] for o in (await client.get(f"/tasks/{gym['id']}/occurrences", headers=auth_a)).json()}
    assert occ[YESTERDAY.isoformat()] == "skipped"  # not missed
    after = [e for e in await history(client, auth_a, gym["id"]) if e["event_type"] == "occurrence_missed"]
    assert len(after) == len(before)                 # no new missed event

    resumed = await client.post(f"/tasks/{gym['id']}/resume", headers=auth_a)
    assert resumed.json()["status"] == "pending"
    assert scheduled((await client.get(base, headers=auth_a)).json())  # reminders planned again


async def test_sweep_cancels_a_paused_tasks_due_reminder(client, auth_a, make_task, db):
    gym = await recurring_with_schedule(client, auth_a, make_task, TODAY)
    time_id = (await client.get(f"/tasks/{gym['id']}/reminder-config/reminder-times", headers=auth_a)).json()[0]["id"]
    await client.post(f"/tasks/{gym['id']}/pause", headers=auth_a)
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    await reminders_repository.bulk_create_deliveries(db, [(gym["id"], time_id, due)])
    await db.commit()
    await reminders_service.run_reminder_sweep(db)
    rows = (await client.get(f"/tasks/{gym['id']}/reminder-config/deliveries", headers=auth_a)).json()
    assert next(d["status"] for d in rows if datetime.fromisoformat(d["scheduled_for"]) == due) == "cancelled"


async def test_pause_rules(client, auth_a, make_task):
    task = await make_task("t")
    url = f"/tasks/{task['id']}"
    assert (await client.patch(url, headers=auth_a, json={"status": "paused"})).status_code == 400  # use /pause
    await client.post(f"{url}/pause", headers=auth_a)
    assert (await client.post(f"{url}/pause", headers=auth_a)).status_code == 400                  # already paused
    assert (await client.patch(url, headers=auth_a, json={"status": "pending"})).status_code == 400  # use /resume
    done = await client.patch(url, headers=auth_a, json={"status": "completed"})                    # allowed
    assert done.json()["status"] == "completed"
    assert (await client.post(f"{url}/pause", headers=auth_a)).status_code == 400                  # completed
    assert (await client.post(f"{url}/resume", headers=auth_a)).status_code == 400                 # not paused


async def test_paused_task_does_not_lower_completion(client, auth_a, make_task):
    done = await make_task("done")
    await client.patch(f"/tasks/{done['id']}", headers=auth_a, json={"status": "completed"})
    on_hold = await make_task("on hold")
    await client.post(f"/tasks/{on_hold['id']}/pause", headers=auth_a)
    assert (await client.get("/dashboard", headers=auth_a)).json()["overall_completion_percentage"] == 100.0
