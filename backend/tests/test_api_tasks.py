"""API tests for tasks: auth, CRUD, ownership isolation, validation,
overdue detection, history, and the Eisenhower matrix. Real DB + real auth."""
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("clean_accounts")


async def test_requires_auth(client):
    assert (await client.get("/tasks")).status_code == 401
    bad = {"Authorization": "Bearer not.a.token"}
    assert (await client.get("/tasks", headers=bad)).status_code == 401


async def test_crud_round_trip(client, auth_a, make_task):
    task = await make_task("Buy milk", description="2 litres")
    assert task["status"] == "pending"

    got = await client.get(f"/tasks/{task['id']}", headers=auth_a)
    assert got.json()["title"] == "Buy milk"

    updated = await client.patch(f"/tasks/{task['id']}", json={"title": "Buy oat milk"}, headers=auth_a)
    assert updated.json()["title"] == "Buy oat milk"

    assert (await client.delete(f"/tasks/{task['id']}", headers=auth_a)).status_code == 204
    assert (await client.get(f"/tasks/{task['id']}", headers=auth_a)).status_code == 404


async def test_other_user_cannot_see_or_touch_task(client, auth_b, make_task):
    task = await make_task("A's private task")
    url = f"/tasks/{task['id']}"
    # 404, never 403 — existence of other users' tasks must not leak.
    assert (await client.get(url, headers=auth_b)).status_code == 404
    assert (await client.patch(url, json={"title": "x"}, headers=auth_b)).status_code == 404
    assert (await client.delete(url, headers=auth_b)).status_code == 404
    for sub in ("/history", "/reminder-config", "/analytics"):
        assert (await client.get(url + sub, headers=auth_b)).status_code == 404
    assert (await client.get("/tasks", headers=auth_b)).json() == []


@pytest.mark.parametrize("field", ["title", "urgent", "important", "status"])
async def test_patch_null_is_422_not_500(client, auth_a, make_task, field):
    task = await make_task()
    response = await client.patch(f"/tasks/{task['id']}", json={field: None}, headers=auth_a)
    assert response.status_code == 422


async def test_patch_null_clears_description(client, auth_a, make_task):
    task = await make_task(description="something")
    response = await client.patch(f"/tasks/{task['id']}", json={"description": None}, headers=auth_a)
    assert response.status_code == 200
    assert response.json()["description"] is None


async def test_due_date_on_recurring_rejected(client, auth_a):
    payload = {"title": "x", "category": "recurring", "urgent": False, "important": False,
               "due_date": date.today().isoformat()}
    assert (await client.post("/tasks", json=payload, headers=auth_a)).status_code == 422


async def test_overdue_detection(client, auth_a, make_task, run_maintenance):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    late = await make_task("late", due_date=yesterday)
    today_all_day = await make_task("today", due_date=date.today().isoformat())
    future = await make_task("future", due_date=tomorrow)

    status = lambda t: t["status"]  # noqa: E731
    await run_maintenance()  # the worker's job; GET /tasks only reads
    tasks = {t["id"]: t for t in (await client.get("/tasks", headers=auth_a)).json()}
    assert status(tasks[late["id"]]) == "overdue"
    assert status(tasks[today_all_day["id"]]) == "pending"  # whole due date counts as on time
    assert status(tasks[future["id"]]) == "pending"


async def test_history_records_reopen(client, auth_a, make_task):
    task = await make_task()
    url = f"/tasks/{task['id']}"
    await client.patch(url, json={"status": "completed"}, headers=auth_a)
    await client.patch(url, json={"status": "pending"}, headers=auth_a)
    events = [e["event_type"] for e in (await client.get(url + "/history", headers=auth_a)).json()]
    assert events == ["created", "status_changed", "reopened"]


async def test_matrix_quadrants(client, auth_a, make_task):
    await make_task("do", urgent=True, important=True)
    await make_task("schedule", important=True)
    await make_task("delegate", urgent=True)
    await make_task("eliminate")
    matrix = (await client.get("/tasks/matrix", headers=auth_a)).json()
    assert {k: [t["title"] for t in v["tasks"]] for k, v in matrix.items()} == {
        "do_first": ["do"],
        "schedule": ["schedule"],
        "delegate": ["delegate"],
        "eliminate": ["eliminate"],
    }


# --- status default consistency (Step 1, item #8) ------------------------------

async def test_status_default_matches_database_and_api(client, auth_a, user_ids, db):
    """The DB stores enum NAMES ('PENDING'); the API speaks VALUES ('pending').
    The model's server_default must be the DB spelling, and a row created by
    the database default (no status given) must read back as 'pending'."""
    from sqlalchemy import text

    from app.features.tasks.models import Task

    assert Task.__table__.c.status.server_default.arg == "PENDING"
    db_default = (await db.execute(text(
        "select column_default from information_schema.columns "
        "where table_schema='public' and table_name='tasks' and column_name='status'"
    ))).scalar()
    assert db_default.startswith("'PENDING'")

    task_id = (await db.execute(text(
        "insert into tasks (user_id, title, category, urgent, important, created_at, updated_at) "
        "values (:uid, 'raw default', 'ONE_TIME', false, false, now(), now()) returning id"
    ), {"uid": user_ids["a"]})).scalar()
    await db.commit()
    response = await client.get(f"/tasks/{task_id}", headers=auth_a)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
