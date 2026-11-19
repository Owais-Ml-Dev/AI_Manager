"""Per-user time zones (Step 2). Uses Pacific/Kiritimati (UTC+14) and
Pacific/Pago_Pago (UTC-11): 25 hours apart, so their calendar dates ALWAYS
differ from each other, and at any hour at least one differs from the
server's (India) date — these tests cannot pass by accident of the clock.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.timezones import is_valid_zone, local_to_utc, today_in, zone
from app.features.assistant import service as assistant_service
from app.features.reminders import repository as reminders_repository
from app.features.reminders import service as reminders_service

pytestmark = pytest.mark.usefixtures("clean_accounts")

KIRITIMATI, PAGO, NEW_YORK = "Pacific/Kiritimati", "Pacific/Pago_Pago", "America/New_York"


async def set_tz(client, headers, name):
    response = await client.put("/me/settings", json={"timezone": name}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def local_today(name: str) -> date:
    return today_in(zone(name))


# --- pure rules ------------------------------------------------------------------

def test_daylight_saving_gap_and_overlap():
    ny = zone(NEW_YORK)
    gap = local_to_utc(date(2026, 3, 8), time(2, 30), ny)       # 02:30 doesn't exist that day
    assert gap.astimezone(ny).time() == time(3, 30)               # -> moment after the jump
    twice = local_to_utc(date(2026, 11, 1), time(1, 30), ny)    # 01:30 happens twice
    assert twice == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)  # -> the first (EDT)


def test_today_depends_on_zone():
    instant = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)
    assert today_in(zone("Asia/Kolkata"), instant) == date(2026, 11, 20)  # 01:30 next day
    assert today_in(zone(NEW_YORK), instant) == date(2026, 11, 19)
    assert today_in(zone(KIRITIMATI), instant) == date(2026, 11, 20)
    assert today_in(zone(PAGO), instant) == date(2026, 11, 19)


def test_zone_names_validated():
    assert all(map(is_valid_zone, ["Asia/Kolkata", "UTC", NEW_YORK]))
    assert not any(map(is_valid_zone, ["IST", "EST", "Mars/Base", "", " Asia/Kolkata"]))


# --- /me/settings ------------------------------------------------------------------

async def test_settings_default_then_set_per_user(client, auth_a, auth_b):
    assert (await client.get("/me/settings", headers=auth_a)).json() == {
        "timezone": "Asia/Kolkata", "is_default": True}
    assert await set_tz(client, auth_a, NEW_YORK) == {"timezone": NEW_YORK, "is_default": False}
    assert (await client.get("/me/settings", headers=auth_a)).json()["timezone"] == NEW_YORK
    assert (await client.get("/me/settings", headers=auth_b)).json()["is_default"] is True  # B untouched

    for bad in ["IST", "Mars/Base", ""]:
        assert (await client.put("/me/settings", json={"timezone": bad}, headers=auth_a)).status_code == 422


# --- overdue, occurrences, reminders in the owner's zone ---------------------------------

async def test_overdue_is_judged_in_each_owners_zone(client, auth_a, auth_b, make_task):
    await set_tz(client, auth_a, KIRITIMATI)
    await set_tz(client, auth_b, PAGO)
    due = local_today(PAGO).isoformat()  # Pago's today = always before Kiritimati's today
    a_task = await make_task("A due", due_date=due)
    b_task = await make_task("B due", due_date=due, headers=auth_b)

    statuses = {t["id"]: t["status"] for t in (await client.get("/tasks", headers=auth_a)).json()}
    assert statuses[a_task["id"]] == "overdue"      # past date in Kiritimati
    b = (await client.get(f"/tasks/{b_task['id']}", headers=auth_b)).json()
    assert b["status"] == "pending"                  # still today in Pago Pago

    # due_time uses local clock time too: 00:00 today has passed, 23:59:59 hasn't.
    today_a = local_today(KIRITIMATI).isoformat()
    passed = await make_task("A passed", due_date=today_a, due_time="00:00:00")
    later = await make_task("A later", due_date=today_a, due_time="23:59:59")
    statuses = {t["id"]: t["status"] for t in (await client.get("/tasks", headers=auth_a)).json()}
    assert statuses[passed["id"]] == "overdue" and statuses[later["id"]] == "pending"


async def test_occurrences_use_owners_today(client, auth_a, auth_b, make_task):
    for headers, name in ((auth_a, KIRITIMATI), (auth_b, PAGO)):
        await set_tz(client, headers, name)
        today = local_today(name)
        task = await make_task(f"gym {name}", category="recurring", headers=headers)
        await client.put(f"/tasks/{task['id']}/reminder-config", headers=headers, json={
            "start_date": (today - timedelta(days=1)).isoformat(), "day_selection_type": "every_day"})
        occ = {o["occurrence_date"]: o["status"]
               for o in (await client.get(f"/tasks/{task['id']}/occurrences", headers=headers)).json()}
        assert occ[(today - timedelta(days=1)).isoformat()] == "missed", name
        assert occ[today.isoformat()] == "pending", name


async def test_reminders_planned_in_owners_zone_and_replanned_on_change(client, auth_a, make_task):
    await set_tz(client, auth_a, NEW_YORK)
    task = await make_task("standup", category="recurring")
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=auth_a, json={
        "start_date": local_today(NEW_YORK).isoformat(), "day_selection_type": "every_day"})
    await client.post(f"{base}/reminder-times", headers=auth_a, json={"time_of_day": "09:00:00"})

    def check(rows, name):
        assert rows, "deliveries expected"
        for d in rows:
            shown = datetime.fromisoformat(d["scheduled_for"])
            local = shown.astimezone(zone(name))
            assert local.time() == time(9, 0)                                   # 09:00 local
            assert shown == local_to_utc(local.date(), time(9, 0), zone(name))  # exact instant
            assert shown.utcoffset() == local.utcoffset()                       # shown in user's zone

    check((await client.get(f"{base}/deliveries", headers=auth_a)).json(), NEW_YORK)

    await set_tz(client, auth_a, "Asia/Kolkata")  # user travels: upcoming reminders move
    rows = [d for d in (await client.get(f"{base}/deliveries", headers=auth_a)).json() if d["status"] == "scheduled"]
    check(rows, "Asia/Kolkata")


async def test_sweep_matches_occurrence_by_owners_local_date(client, auth_a, make_task, db):
    # A delivery due now belongs to the owner's LOCAL today. If the sweep used
    # the UTC/server date it could miss that today's occurrence is completed
    # and send a reminder for a finished day.
    # Pick whichever zone's date differs from the UTC date right now (one
    # always does), so the UTC-date bug is caught at any hour.
    utc_today = datetime.now(timezone.utc).date()
    name = KIRITIMATI if local_today(KIRITIMATI) != utc_today else PAGO
    assert local_today(name) != utc_today
    await set_tz(client, auth_a, name)
    today = local_today(name)
    task = await make_task("gym", category="recurring")
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=auth_a, json={"start_date": today.isoformat(), "day_selection_type": "every_day"})
    time_id = (await client.post(f"{base}/reminder-times", headers=auth_a,
                                 json={"time_of_day": "23:59:59"})).json()["id"]
    occ = next(o for o in (await client.get(f"/tasks/{task['id']}/occurrences", headers=auth_a)).json()
               if o["occurrence_date"] == today.isoformat())
    await client.patch(f"/tasks/{task['id']}/occurrences/{occ['id']}", headers=auth_a, json={"status": "completed"})

    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    await reminders_repository.bulk_create_deliveries(db, [(task["id"], time_id, due)])
    db.expire_all()
    await reminders_service.run_reminder_sweep(db)

    rows = (await client.get(f"{base}/deliveries", headers=auth_a)).json()
    status = next(d["status"] for d in rows if datetime.fromisoformat(d["scheduled_for"]) == due)
    assert status == "cancelled"


# --- history + assistant -----------------------------------------------------------------

async def test_history_times_shown_in_users_zone(client, auth_a, make_task):
    await set_tz(client, auth_a, NEW_YORK)
    task = await make_task("t")
    event = (await client.get(f"/tasks/{task['id']}/history", headers=auth_a)).json()[0]
    shown = datetime.fromisoformat(event["occurred_at"])
    assert shown.utcoffset() == shown.astimezone(zone(NEW_YORK)).utcoffset()


async def test_assistant_resolves_dates_from_users_today(client, auth_a, monkeypatch):
    await set_tz(client, auth_a, KIRITIMATI)
    prompts = []

    async def capture(prompt):
        prompts.append(prompt)
        return {"intent": "unknown"}

    monkeypatch.setattr(assistant_service, "generate_json", capture)
    await client.post("/assistant/message", headers=auth_a, json={"message": "remind me tomorrow"})
    assert f"Today's date is {local_today(KIRITIMATI).isoformat()}." in prompts[0]
