"""Step 5: in-app inbox, device registration, FCM push from the reminder
worker. Real DB + real sweep; only Google's network is replaced (fake FCM
send, or an httpx MockTransport for the auth/send protocol tests)."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import fcm
from app.core.config import settings
from app.core.timezones import today_in, zone
from app.features.notifications import service as notifications_service
from app.features.reminders import repository as reminders_repository
from app.features.reminders import service as reminders_service

pytestmark = pytest.mark.usefixtures("clean_accounts")

TODAY = today_in(zone("Asia/Kolkata"))
TOKEN_1 = "device-token-one-" + "a" * 40
TOKEN_2 = "device-token-two-" + "b" * 40


@pytest.fixture
def fake_fcm(monkeypatch):
    """Pretends Firebase is configured; records pushes. outcomes[token] =
    "sent" (default) | "invalid_token" | "retryable" | "error"."""
    sent, outcomes = [], {}

    async def fake_send(token, title, body, data, validate_only=False):
        sent.append({"token": token, "title": title, "body": body, "data": data})
        return fcm.SendResult(outcomes.get(token, "sent"))

    monkeypatch.setattr(fcm, "is_configured", lambda: True)
    monkeypatch.setattr(fcm, "send", fake_send)
    return sent, outcomes


@pytest.fixture(autouse=True)
async def _wipe_devices_and_inbox(user_ids):
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async def wipe():
        async with AsyncSessionLocal() as s:
            ids = list(user_ids.values())
            await s.execute(text("delete from device_tokens where user_id = any(:ids)"), {"ids": ids})
            await s.execute(text("delete from notifications where user_id = any(:ids)"), {"ids": ids})
            await s.commit()
    await wipe()
    yield
    await wipe()


async def due_reminder(client, headers, make_task, db, title="Pay rent"):
    """A one-time task with one reminder delivery due 1 minute ago (committed)."""
    task = await make_task(title, due_date=TODAY.isoformat())
    base = f"/tasks/{task['id']}/reminder-config"
    await client.put(base, headers=headers, json={
        "start_date": TODAY.isoformat(), "end_date": TODAY.isoformat(), "day_selection_type": "every_day"})
    time_id = (await client.post(f"{base}/reminder-times", headers=headers, json={"time_of_day": "23:59:59"})).json()["id"]
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    await reminders_repository.bulk_create_deliveries(db, [(task["id"], time_id, due)])
    await db.commit()
    return task, due


async def inbox(client, headers, **params):
    return (await client.get("/notifications", headers=headers, params=params)).json()


# --- devices ----------------------------------------------------------------------

async def test_device_registration_and_ownership(client, auth_a, auth_b):
    created = await client.post("/devices", headers=auth_a, json={"token": TOKEN_1, "platform": "android"})
    assert created.status_code == 201
    assert created.json()["token_suffix"] == TOKEN_1[-8:] and "token" not in created.json()
    assert len((await client.get("/devices", headers=auth_a)).json()) == 1

    # The same phone logs into another account: the token moves.
    await client.post("/devices", headers=auth_b, json={"token": TOKEN_1})
    assert (await client.get("/devices", headers=auth_a)).json() == []
    assert (await client.delete(f"/devices/{TOKEN_1}", headers=auth_a)).status_code == 404  # not A's
    assert (await client.delete(f"/devices/{TOKEN_1}", headers=auth_b)).status_code == 204
    assert (await client.post("/devices", headers=auth_a, json={"token": "short"})).status_code == 422


# --- reminder -> inbox + push --------------------------------------------------------

async def test_due_reminder_goes_to_inbox_and_every_device(client, auth_a, make_task, db, fake_fcm):
    sent, _ = fake_fcm
    for token in (TOKEN_1, TOKEN_2):
        await client.post("/devices", headers=auth_a, json={"token": token})
    task, due = await due_reminder(client, auth_a, make_task, db)

    assert await reminders_service.run_reminder_sweep(db) == 1

    [entry] = await inbox(client, auth_a)
    local = due.astimezone(zone("Asia/Kolkata"))
    assert (entry["task_id"], entry["title"], entry["body"]) == (task["id"], "Pay rent", f"Reminder for {local:%H:%M}")
    assert entry["push_status"] == "sent" and entry["read_at"] is None
    assert entry["created_at"].endswith("+05:30")  # shown in the user's zone
    assert {p["token"] for p in sent} == {TOKEN_1, TOKEN_2}
    assert sent[0]["data"]["type"] == "reminder" and sent[0]["data"]["task_id"] == str(task["id"])


async def test_dead_device_token_is_removed(client, auth_a, make_task, db, fake_fcm):
    _, outcomes = fake_fcm
    outcomes[TOKEN_1] = "invalid_token"  # app uninstalled on that phone
    for token in (TOKEN_1, TOKEN_2):
        await client.post("/devices", headers=auth_a, json={"token": token})
    await due_reminder(client, auth_a, make_task, db)
    await reminders_service.run_reminder_sweep(db)
    assert [d["token_suffix"] for d in (await client.get("/devices", headers=auth_a)).json()] == [TOKEN_2[-8:]]
    assert (await inbox(client, auth_a))[0]["push_status"] == "sent"


async def test_inbox_still_gets_reminder_without_push(client, auth_a, make_task, db, fake_fcm, monkeypatch):
    await due_reminder(client, auth_a, make_task, db, "No phone yet")
    await reminders_service.run_reminder_sweep(db)
    assert (await inbox(client, auth_a))[0]["push_status"] == "no_devices"

    monkeypatch.setattr(fcm, "is_configured", lambda: False)  # Firebase not set up
    await due_reminder(client, auth_a, make_task, db, "Push off")
    await reminders_service.run_reminder_sweep(db)
    assert {n["title"]: n["push_status"] for n in await inbox(client, auth_a)}["Push off"] == "disabled"


async def test_push_failure_never_loses_the_inbox_entry(client, auth_a, make_task, db, fake_fcm):
    _, outcomes = fake_fcm
    outcomes[TOKEN_1] = "retryable"  # FCM down
    await client.post("/devices", headers=auth_a, json={"token": TOKEN_1})
    await due_reminder(client, auth_a, make_task, db)
    await reminders_service.run_reminder_sweep(db)
    assert (await inbox(client, auth_a))[0]["push_status"] == "failed"
    assert len((await client.get("/devices", headers=auth_a)).json()) == 1  # not a dead token


async def test_push_crash_is_recorded_as_failed(client, auth_a, make_task, db, monkeypatch):
    async def crash(*args, **kwargs):
        raise RuntimeError("network stack exploded")

    monkeypatch.setattr(fcm, "is_configured", lambda: True)
    monkeypatch.setattr(fcm, "send", crash)
    await client.post("/devices", headers=auth_a, json={"token": TOKEN_1})
    await due_reminder(client, auth_a, make_task, db)
    assert await reminders_service.run_reminder_sweep(db) == 1
    assert (await inbox(client, auth_a))[0]["push_status"] == "failed"  # entry kept, outcome honest


async def test_one_notification_per_reminder(client, auth_a, make_task, db, fake_fcm):
    sent, _ = fake_fcm
    await client.post("/devices", headers=auth_a, json={"token": TOKEN_1})
    task, due = await due_reminder(client, auth_a, make_task, db)
    delivery = next(d for d in await reminders_repository.list_deliveries_by_task(db, task["id"])
                    if d.scheduled_for == due)
    from app.features.tasks import repository as tasks_repository
    task_row = await tasks_repository.get(db, task["id"])
    assert await notifications_service.deliver_reminder(db, task_row, delivery) == "sent"
    assert await notifications_service.deliver_reminder(db, task_row, delivery) == "duplicate"
    assert len(await inbox(client, auth_a)) == 1 and len(sent) == 1


# --- inbox endpoints -----------------------------------------------------------------

async def test_inbox_read_state_and_privacy(client, auth_a, auth_b, make_task, db, fake_fcm):
    await due_reminder(client, auth_a, make_task, db, "First")
    await due_reminder(client, auth_a, make_task, db, "Second")
    await reminders_service.run_reminder_sweep(db)
    assert (await client.get("/notifications/unread-count", headers=auth_a)).json() == {"unread": 2}

    first = (await inbox(client, auth_a))[-1]
    assert (await client.post(f"/notifications/{first['id']}/read", headers=auth_b)).status_code == 404  # B can't
    assert await inbox(client, auth_b) == []
    read = (await client.post(f"/notifications/{first['id']}/read", headers=auth_a)).json()
    assert read["read_at"] is not None
    assert [n["title"] for n in await inbox(client, auth_a, unread_only=True)] == ["Second"]
    assert (await client.post("/notifications/read-all", headers=auth_a)).json() == {"unread": 0}


# --- FCM protocol (auth + message format), Google replaced by MockTransport ----------

@pytest.fixture
def service_account(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    path = tmp_path / "firebase-service-account.json"
    path.write_text(json.dumps({"project_id": "demo-project", "client_email": "push@demo-project.iam.gserviceaccount.com",
                                "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setattr(settings, "firebase_credentials_file", str(path))
    for name, value in (("_credentials", None), ("_access_token", None), ("_token_expires_at", 0.0)):
        monkeypatch.setattr(fcm, name, value)
    return key.public_key()


def test_message_format_for_android():
    msg = fcm.build_message("tok", "Pay rent", "Reminder for 09:00", {"task_id": "7"})["message"]
    assert msg["android"] == {"priority": "HIGH", "ttl": "3600s",
                              "notification": {"channel_id": "task_reminders", "tag": "7"}}
    assert msg["notification"] == {"title": "Pay rent", "body": "Reminder for 09:00"}


def test_fcm_error_classification():
    def r(status, error):
        return httpx.Response(status, json={"error": error})
    unregistered = {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}
    bad_token = {"status": "INVALID_ARGUMENT", "message": "The registration token is not a valid FCM registration token"}
    assert fcm.classify(httpx.Response(200, json={"name": "x"})).outcome == "sent"
    assert fcm.classify(r(404, unregistered)).outcome == "invalid_token"
    assert fcm.classify(r(400, bad_token)).outcome == "invalid_token"
    assert fcm.classify(r(429, {"status": "RESOURCE_EXHAUSTED", "details": [{"errorCode": "QUOTA_EXCEEDED"}]})).outcome == "retryable"
    assert fcm.classify(r(503, {"status": "UNAVAILABLE"})).outcome == "retryable"
    assert fcm.classify(r(401, {"status": "UNAUTHENTICATED"})).outcome == "error"


async def test_fcm_auth_and_send_protocol(service_account, monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            claims = jwt.decode(form["assertion"], service_account, algorithms=["RS256"],
                                audience="https://oauth2.googleapis.com/token")
            assert claims["iss"] == "push@demo-project.iam.gserviceaccount.com"
            assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
            assert claims["exp"] - claims["iat"] == 3600
            return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3599})
        assert request.url.path == "/v1/projects/demo-project/messages:send"
        assert request.headers["authorization"] == "Bearer ya29.test"
        return httpx.Response(200, json={"name": "projects/demo-project/messages/1"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(fcm.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    first = await fcm.send("tok-1", "t", "b", {"task_id": "1"})
    second = await fcm.send("tok-2", "t", "b", {"task_id": "1"}, validate_only=True)
    assert (first.outcome, second.outcome) == ("sent", "sent")
    token_calls = [c for c in calls if c.url.host == "oauth2.googleapis.com"]
    assert len(token_calls) == 1  # access token cached for the second send
    assert json.loads(calls[-1].content)["validate_only"] is True


async def test_fcm_rejected_credentials_raise_config_error(service_account, monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(fcm.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "invalid_grant"})), **kw))
    with pytest.raises(fcm.FcmConfigError):
        await fcm.send("tok", "t", "b", {})
