"""Shared memory of which Gemini models are out of quota (or retired).

Each model in settings.gemini_model_chain has its own free-tier quota. When
Google refuses a model with HTTP 429 (quota) or 404 (model retired), we
record that in Redis with an expiry equal to Google's own reset time
(RetryInfo.retryDelay). Every request reads this first and skips those models,
so an exhausted model is never called again until its key expires — at which
point it is automatically first in line again. No timers, no clocks: Redis
TTL does the restoring.

Redis (not process memory) because several server processes may run at once
and must agree. If Redis is unreachable we fail OPEN (treat every model as
available): the fallback must never be the thing that breaks the assistant —
worst case is one wasted call that gets a 429 and moves on.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.redis import redis_client

logger = logging.getLogger("gemini")

_KEY_PREFIX = "gemini:exhausted:"
# Used only when Google gives no retryDelay. Per-minute limits clear within a
# minute. For daily limits (and anything unrecognised) we don't guess the
# reset time: skip for an hour, then one request checks again — at most one
# quick failed call per hour per model.
_DEFAULT_SKIP_SECONDS = {"minute": 60, "day": 3600, "unknown": 60}
_RETIRED_SKIP_SECONDS = 24 * 3600


@dataclass
class QuotaHit:
    kind: str        # "minute" | "day" | "unknown" | "retired"
    seconds: float   # how long to skip the model
    detail: str      # quota id / message, for logs


def _key(model: str) -> str:
    return f"{_KEY_PREFIX}{model}"


def parse_quota_error(response: httpx.Response) -> QuotaHit:
    """Reads Google's 429 body: which limit (per-minute/per-day) and when it
    resets. Tolerates any shape — an unreadable body becomes a short skip, so
    a format change can never lock a model out for a day."""
    if response.status_code == 404:
        return QuotaHit("retired", _RETIRED_SKIP_SECONDS, response.text[:200])
    kind, detail, seconds = "unknown", "", None
    try:
        for d in response.json().get("error", {}).get("details", []):
            for v in d.get("violations", []):
                quota_id = v.get("quotaId", "")
                detail = detail or quota_id
                if "PerDay" in quota_id:
                    kind = "day"
                elif "PerMinute" in quota_id and kind != "day":
                    kind = "minute"
            match = re.fullmatch(r"([\d.]+)s", str(d.get("retryDelay", "")))
            if match:
                seconds = float(match.group(1))
    except (ValueError, AttributeError, TypeError):
        pass
    if seconds is None or seconds <= 0:
        seconds = _DEFAULT_SKIP_SECONDS[kind]
    return QuotaHit(kind, seconds, detail)


async def unavailable_models(models: list[str]) -> dict[str, datetime]:
    """{model: available_again_at (UTC)} for models currently marked
    exhausted. Empty on any Redis failure (fail open)."""
    try:
        values = await redis_client.mget([_key(m) for m in models])
    except Exception as exc:  # noqa: BLE001 - fail open, by design
        logger.warning("Gemini quota state unreadable (Redis), trying all models: %s", exc)
        return {}
    result = {}
    for model, raw in zip(models, values):
        if raw is None:
            continue
        try:
            result[model] = datetime.fromisoformat(json.loads(raw)["until"])
        except (ValueError, KeyError, TypeError):
            result[model] = datetime.now(timezone.utc) + timedelta(seconds=60)
    return result


async def mark_unavailable(model: str, hit: QuotaHit) -> None:
    """Skip `model` for hit.seconds. Logged once per transition, not per
    request (requests that find it marked never call it)."""
    until = datetime.now(timezone.utc) + timedelta(seconds=hit.seconds)
    value = json.dumps({"kind": hit.kind, "until": until.isoformat(), "detail": hit.detail})
    try:
        await redis_client.set(_key(model), value, ex=max(1, int(round(hit.seconds))))
    except Exception as exc:  # noqa: BLE001 - fail open, by design
        logger.warning("Could not record Gemini quota state for %s: %s", model, exc)
        return
    log = logger.error if hit.kind == "retired" else logger.warning
    log("Gemini model %s unavailable (%s limit) — skipping it for %.0fs, until %s UTC. %s",
        model, hit.kind, hit.seconds, until.strftime("%H:%M:%S"), hit.detail)


async def status(models: list[str]) -> dict[str, str]:
    """Per-model availability for /health."""
    down = await unavailable_models(models)
    now = datetime.now(timezone.utc)
    return {
        m: (f"exhausted, available again in {max(0, int((down[m] - now).total_seconds()))}s"
            if m in down else "available")
        for m in models
    }
