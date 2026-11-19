"""Gemini model fallback + quota memory. Real Redis (the shared state is the
point), fake Gemini network: `_post_once` is replaced by a script of replies
per model, and every call is recorded so tests can prove exhausted models are
skipped WITHOUT being called. Uses made-up model names so these tests can
never mark the real models exhausted.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core import gemini, gemini_quota
from app.core.config import settings
from app.core.redis import redis_client

A, B, C = "aitm-test-model-a", "aitm-test-model-b", "aitm-test-model-c"


def ok(text='{"intent": "unknown"}'):
    return httpx.Response(200, json={"candidates": [
        {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def cut_off():  # the real failure seen live: valid start, cut mid-object, finishReason=STOP
    return ok('{"intent": "delete_task", "title": "Water the plants",')


def quota(kind="Day", delay="30s"):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": f"GenerateRequestsPer{kind}PerProjectPerModel-FreeTier"}]}]
    if delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    return httpx.Response(429, json={"error": {"code": 429, "details": details}})


@pytest.fixture
async def fake_gemini(monkeypatch):
    """Returns (script, calls): script[model] = list of replies/exceptions
    consumed in order; calls = models actually called, in order."""
    script, calls = {A: [], B: [], C: []}, []

    async def fake_post(prompt, model, timeout=gemini._TIMEOUT_SECONDS):
        calls.append(model)
        if not script[model]:
            raise AssertionError(f"{model} was called but has no scripted reply")
        reply = script[model].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(settings, "gemini_models", f"{A},{B},{C}")
    monkeypatch.setattr(gemini, "_post_once", fake_post)
    monkeypatch.setattr(gemini, "_RETRY_DELAY_SECONDS", 0)
    keys = [f"gemini:exhausted:{m}" for m in (A, B, C)]
    await redis_client.delete(*keys)
    yield script, calls
    await redis_client.delete(*keys)


async def test_users_example_exhausted_models_are_skipped(fake_gemini):
    script, calls = fake_gemini

    # Request 1: A out of quota -> marked, same request switches to B.
    script[A] += [quota()]
    script[B] += [ok()]
    await gemini.generate_json("p")
    assert calls == [A, B]

    # Request 2: straight to B — A is NOT called (it has no scripted reply,
    # so calling it would fail this test).
    calls.clear()
    script[B] += [ok()]
    await gemini.generate_json("p")
    assert calls == [B]

    # Request 3: B out of quota -> C.
    calls.clear()
    script[B] += [quota()]
    script[C] += [ok()]
    await gemini.generate_json("p")
    assert calls == [B, C]

    # Request 4: straight to C.
    calls.clear()
    script[C] += [ok()]
    await gemini.generate_json("p")
    assert calls == [C]

    status = await gemini_quota.status([A, B, C])
    assert status[C] == "available" and "exhausted" in status[A] and "exhausted" in status[B]


async def test_all_exhausted_reports_reset_time_without_calling_anyone(fake_gemini):
    script, calls = fake_gemini
    script[A] += [quota(delay="300s")]
    script[B] += [quota(delay="120s")]
    script[C] += [quota(delay="900s")]
    with pytest.raises(gemini.GeminiQuotaExhaustedError) as first:
        await gemini.generate_json("p")
    assert calls == [A, B, C]
    soonest = first.value.available_at - datetime.now(timezone.utc)
    assert timedelta(seconds=100) < soonest <= timedelta(seconds=120)  # B's reset

    calls.clear()
    with pytest.raises(gemini.GeminiQuotaExhaustedError):
        await gemini.generate_json("p")
    assert calls == []  # nothing wasted on known-exhausted models


async def test_model_comes_back_when_its_quota_resets(fake_gemini):
    script, calls = fake_gemini
    script[A] += [quota(kind="Minute", delay="1s"), ok()]
    script[B] += [ok()]
    await gemini.generate_json("p")
    assert calls == [A, B]

    await asyncio.sleep(1.3)  # Redis key expires = quota reset
    calls.clear()
    await gemini.generate_json("p")
    assert calls == [A]  # primary first again, automatically


async def test_slowness_and_overload_never_switch_models(fake_gemini):
    script, calls = fake_gemini
    script[A] += [httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow")]
    with pytest.raises(gemini.GeminiUnavailableError) as exc:
        await gemini.generate_json("p")
    assert not isinstance(exc.value, gemini.GeminiQuotaExhaustedError)
    assert calls == [A, A]  # one retry on the same model, no backup

    calls.clear()
    script[A] += [httpx.Response(503, text="overloaded"), ok()]
    await gemini.generate_json("p")
    assert calls == [A, A]
    assert await gemini_quota.unavailable_models([A, B, C]) == {}  # nothing marked


async def test_cut_off_answer_is_retried_once_on_same_model(fake_gemini):
    script, calls = fake_gemini
    script[A] += [cut_off(), ok('{"intent": "retrieve_tasks"}')]
    assert await gemini.generate_json("p") == {"intent": "retrieve_tasks"}
    assert calls == [A, A]

    calls.clear()
    script[A] += [cut_off(), cut_off()]
    with pytest.raises(gemini.GeminiError):
        await gemini.generate_json("p")
    assert calls == [A, A]


async def test_retired_model_is_skipped_for_a_long_time(fake_gemini):
    script, calls = fake_gemini
    script[A] += [httpx.Response(404, json={"error": {"message": "no longer available"}})]
    script[B] += [ok()]
    await gemini.generate_json("p")
    assert calls == [A, B]
    ttl = await redis_client.ttl(f"gemini:exhausted:{A}")
    assert ttl > 23 * 3600


async def test_redis_failure_fails_open(fake_gemini, monkeypatch):
    script, calls = fake_gemini

    async def broken(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_client, "mget", broken)
    script[A] += [ok()]
    await gemini.generate_json("p")
    assert calls == [A]  # assistant still works; just no quota memory
