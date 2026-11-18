"""Shared test fixtures.

- `client`: in-process HTTP client against the real FastAPI app (real auth,
  real Supabase Postgres, real Upstash Redis). The app's lifespan isn't run,
  so the background reminder worker stays off and tests stay deterministic.
- Two dedicated Supabase accounts (A and B), credentials in backend/.env.test,
  created on first run. API tests use `clean_accounts`, which wipes both
  accounts' tasks (cascading to everything else) and assistant state before
  and after each test.

Run from the backend/ directory: `pytest`.
"""
import os
from pathlib import Path

import httpx
import jwt
import pytest
from dotenv import load_dotenv
from pytest_asyncio import is_async_test
from sqlalchemy import delete as sql_delete

load_dotenv(Path(__file__).resolve().parent.parent / ".env.test")

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.features.assistant import conversation_state  # noqa: E402
from app.features.tasks.models import Task  # noqa: E402
from app.main import app  # noqa: E402

_REQUIRED_ENV = [
    "SUPABASE_ANON_KEY",
    "TEST_USER_A_EMAIL",
    "TEST_USER_A_PASSWORD",
    "TEST_USER_B_EMAIL",
    "TEST_USER_B_PASSWORD",
]


def pytest_collection_modifyitems(items):
    # One shared event loop for all async tests (see pytest.ini).
    marker = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if is_async_test(item):
            item.add_marker(marker, append=False)


async def _get_token(email: str, password: str) -> str:
    """Logs the test account in, signing it up first if it doesn't exist yet."""
    headers = {"apikey": os.environ["SUPABASE_ANON_KEY"]}
    async with httpx.AsyncClient(
        base_url=f"{settings.supabase_url}/auth/v1", headers=headers, timeout=20
    ) as auth:
        login = await auth.post(
            "/token", params={"grant_type": "password"}, json={"email": email, "password": password}
        )
        if login.status_code == 200:
            return login.json()["access_token"]
        signup = (await auth.post("/signup", json={"email": email, "password": password})).json()
        if "access_token" not in signup:
            pytest.exit(
                f"Could not create test account {email}: {signup}. "
                "Is 'Confirm email' turned off in Supabase Auth?"
            )
        return signup["access_token"]


@pytest.fixture(scope="session")
def _env():
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.exit(f"Missing in backend/.env.test: {', '.join(missing)}")


@pytest.fixture(scope="session")
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.fixture(scope="session")
async def tokens(_env):
    return {
        "a": await _get_token(os.environ["TEST_USER_A_EMAIL"], os.environ["TEST_USER_A_PASSWORD"]),
        "b": await _get_token(os.environ["TEST_USER_B_EMAIL"], os.environ["TEST_USER_B_PASSWORD"]),
    }


@pytest.fixture(scope="session")
def auth_a(tokens):
    return {"Authorization": f"Bearer {tokens['a']}"}


@pytest.fixture(scope="session")
def auth_b(tokens):
    return {"Authorization": f"Bearer {tokens['b']}"}


@pytest.fixture(scope="session")
def user_ids(tokens):
    import uuid

    sub = lambda t: uuid.UUID(jwt.decode(t, options={"verify_signature": False})["sub"])  # noqa: E731
    return {"a": sub(tokens["a"]), "b": sub(tokens["b"])}


async def _wipe(user_ids) -> None:
    # One SQL DELETE instead of list + N HTTP deletes: every DB round trip
    # costs ~190ms against the Tokyo-hosted project. DB-level ON DELETE
    # CASCADE removes reminder configs/times, deliveries, occurrences and
    # history along with the tasks.
    async with AsyncSessionLocal() as session:
        await session.execute(sql_delete(Task).where(Task.user_id.in_(list(user_ids.values()))))
        await session.commit()
    for user_id in user_ids.values():
        await conversation_state.clear_pending(user_id)


@pytest.fixture
async def clean_accounts(user_ids):
    await _wipe(user_ids)
    yield
    await _wipe(user_ids)


@pytest.fixture
async def db():
    """A raw DB session, for calling service/repository functions directly."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
def make_task(client, auth_a):
    """Factory: creates a task as user A (or `headers=`) and returns its JSON."""

    async def _make(title="Test task", category="one_time", headers=None, **fields):
        payload = {"title": title, "category": category, "urgent": False, "important": False, **fields}
        response = await client.post("/tasks", json=payload, headers=headers or auth_a)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
