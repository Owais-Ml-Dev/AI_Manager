"""API tests for the read-only analytics: dashboard, per-task analytics,
calendar, and the monthly report. Expected numbers are derived by hand from
a small fixed scenario, so a wrong formula fails loudly."""
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("clean_accounts")

TODAY = date.today()
PAST = TODAY - timedelta(days=3)


async def test_empty_dashboard(client, auth_a):
    dashboard = (await client.get("/dashboard", headers=auth_a)).json()
    assert dashboard["total_tasks"] == 0
    assert dashboard["overall_completion_percentage"] == 0.0


@pytest.fixture
async def scenario(client, auth_a, make_task):
    """1 completed + 1 pending one-time task (both due today), and 1 recurring
    every-day task started 3 days ago with only today's occurrence completed.
    => occurrences: 3 missed + 1 completed are eligible (future ones excluded).
    """
    done = await make_task("done", due_date=TODAY.isoformat())
    await client.patch(f"/tasks/{done['id']}", json={"status": "completed"}, headers=auth_a)
    await make_task("open", due_date=TODAY.isoformat())

    gym = await make_task("gym", category="recurring")
    await client.put(
        f"/tasks/{gym['id']}/reminder-config",
        json={"start_date": PAST.isoformat(), "day_selection_type": "every_day"},
        headers=auth_a,
    )
    occurrences = (await client.get(f"/tasks/{gym['id']}/occurrences", headers=auth_a)).json()
    today = next(o for o in occurrences if o["occurrence_date"] == TODAY.isoformat())
    await client.patch(
        f"/tasks/{gym['id']}/occurrences/{today['id']}", json={"status": "completed"}, headers=auth_a
    )
    return gym


async def test_dashboard_numbers(client, auth_a, scenario):
    d = (await client.get("/dashboard", headers=auth_a)).json()
    assert d["total_tasks"] == 3
    assert d["active_recurring_tasks"] == 1
    assert d["completed_one_time_tasks"] == 1
    assert d["pending_one_time_tasks"] == 1
    assert d["today_completed_occurrences"] == 1
    # (1 one-time + 1 occurrence completed) / (2 one-time + 4 eligible occurrences)
    assert d["overall_completion_percentage"] == 33.3


async def test_task_analytics_excludes_future_occurrences(client, auth_a, scenario):
    a = (await client.get(f"/tasks/{scenario['id']}/analytics", headers=auth_a)).json()
    assert a["missed_occurrences"] == 3
    assert a["completed_occurrences"] == 1
    assert a["completion_percentage"] == 25.0  # 1 / (3 missed + 1 completed)


async def test_calendar_views(client, auth_a, make_task):
    await make_task("dentist", due_date=TODAY.isoformat())
    week = (await client.get(f"/calendar?view=weekly&anchor_date={TODAY}", headers=auth_a)).json()
    assert len(week["days"]) == 7
    assert date.fromisoformat(week["start_date"]).isoweekday() == 1

    day = (await client.get(f"/calendar?view=daily&anchor_date={TODAY}", headers=auth_a)).json()
    [entry] = day["days"][0]["activities"]
    assert (entry["title"], entry["entry_type"]) == ("dentist", "due_date")


async def test_monthly_report(client, auth_a, scenario):
    if PAST.month != TODAY.month:
        pytest.skip("scenario's past days fall in the previous month")
    r = (
        await client.get(f"/reports/monthly?year={TODAY.year}&month={TODAY.month}", headers=auth_a)
    ).json()
    assert r["one_time_performance"]["completion_percentage"] == 50.0  # 1 done / 2 due this month
    assert r["recurring_performance"]["completion_rate"] == 25.0
    [gym] = r["individual_task_performance"]
    # Regression: per-task % used to count future days in its denominator.
    assert gym["completion_percentage"] == 25.0
