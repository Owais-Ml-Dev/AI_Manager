"""Thin client for Gemini's generateContent REST API.

Gemini's ONLY job in this app is natural-language understanding: turn a
message into structured JSON. It never executes anything — the caller
(app.features.assistant) validates the JSON with Pydantic and only acts on
an explicit allowlist of intents. If Gemini is unavailable, callers should
degrade to "I couldn't understand that" rather than fail the whole request.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core import gemini_quota
from app.core.config import settings

logger = logging.getLogger("gemini")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# 503 from Gemini means "temporarily overloaded, try again" per its own error
# message — observed in practice, worth one retry before giving up.
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 1.5
# gemini-3.1-flash-lite answers in ~1.5s (median), but real answers can take
# 4-8s. Measured 2026-11-19: 4s per attempt cut off real answers (2 of ~20
# messages got "busy" after both attempts timed out); 8s gave 0 user-visible
# failures in 33 calls, the occasional stuck call recovering on the retry.
# Worst case ~17.5s (8 + 1.5 delay + 8) before the user is told to retry.
_TIMEOUT_SECONDS = 8.0


class GeminiError(Exception):
    """Gemini's answer couldn't be used (bad shape, not JSON, 4xx)."""


class GeminiUnavailableError(GeminiError):
    """Gemini is down, overloaded or too slow (timeout, network, 5xx) —
    worth telling the user to try again, unlike a GeminiError."""


class GeminiQuotaExhaustedError(GeminiUnavailableError):
    """Every model in the fallback chain is out of quota (or retired).
    `available_at` (UTC) is when the first one comes back."""

    def __init__(self, available_at: datetime):
        super().__init__(f"All Gemini models out of quota until {available_at.isoformat()}")
        self.available_at = available_at


class _ModelUnavailable(Exception):
    """Internal: this model refused with 429 (quota) / 404 (retired) —
    the fallback loop marks it and moves to the next model."""

    def __init__(self, hit: gemini_quota.QuotaHit):
        super().__init__(hit.detail)
        self.hit = hit


async def _post_once(prompt: str, model: str, timeout: float = _TIMEOUT_SECONDS) -> httpx.Response:
    url = f"{_API_BASE}/{model}:generateContent"
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                # Some models "think" before answering (hidden reasoning
                # consumes output tokens); a generous budget keeps that from
                # truncating the JSON. responseMimeType makes Gemini emit
                # JSON only (no prose/markdown), which guards against the
                # rare malformed answers seen in testing. Python still
                # validates everything it returns.
                "generationConfig": {"maxOutputTokens": 2048, "responseMimeType": "application/json"},
            },
        )


def _parse_answer(response: httpx.Response) -> dict:
    """Extracts Gemini's JSON answer. Raises GeminiError if it's unusable
    (bad shape, or not valid JSON — e.g. the rare answer Gemini cuts off
    mid-object while still reporting finishReason=STOP)."""
    try:
        data = response.json()
        candidate = data["candidates"][0]
        # An answer can arrive split across several parts; read them all.
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Unexpected Gemini response shape: %s — body: %s", exc, response.text[:300])
        raise GeminiError(f"Unexpected Gemini response shape: {exc}") from exc

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini did not return valid JSON (finishReason=%s, model=%s): %s",
                       candidate.get("finishReason"), data.get("modelVersion"), text[:300])
        raise GeminiError(f"Gemini did not return valid JSON: {text[:300]}") from exc


async def generate_json(prompt: str) -> dict:
    """Sends `prompt` to Gemini and parses its response as JSON, using the
    first model in settings.gemini_model_chain that isn't out of quota.

    Fallback (quota only): a 429 / 404 marks that model unavailable in Redis
    until Google's reset time and the SAME request immediately moves to the
    next model — no delay, no retrying the refused model. Later requests skip
    marked models without calling them. Slowness/overload (timeout, 503) is
    NOT quota: it gets the usual one retry on the same model and never
    switches models, so a slow moment can't push everyone onto the slower
    backups.

    Raises GeminiQuotaExhaustedError (every model out of quota),
    GeminiUnavailableError (down/slow) or GeminiError (unusable answer) —
    callers treat Gemini's output as untrusted and degrade to a message.
    """
    models = settings.gemini_model_chain
    unavailable = await gemini_quota.unavailable_models(models)
    for model in models:
        if model in unavailable:
            continue
        try:
            return await _generate_with_model(prompt, model)
        except _ModelUnavailable as exc:
            await gemini_quota.mark_unavailable(model, exc.hit)
            unavailable[model] = datetime.now(timezone.utc) + timedelta(seconds=exc.hit.seconds)
    raise GeminiQuotaExhaustedError(min(unavailable.values()))


async def _generate_with_model(prompt: str, model: str) -> dict:
    """One model, with one retry (after _RETRY_DELAY_SECONDS) for transient
    failures: network error/timeout, 503 overloaded, or an unusable answer
    (measured: a cut-off answer is a one-off; the same request then answers
    correctly). Every failure is logged here first, since callers degrade to
    a generic message that would otherwise hide the real cause.
    (Hedged duplicate requests were tried 2026-11-19 and removed: when Gemini
    is slow both copies usually are — the duplicate won 2 of 13 times — and
    the extra calls exhausted the free per-minute quota, causing 429s.)
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        last_attempt = attempt == _MAX_ATTEMPTS
        try:
            response = await _post_once(prompt, model)
        except httpx.HTTPError as exc:
            logger.warning("Gemini %s request failed (attempt %d): %s %s",
                           model, attempt, type(exc).__name__, exc)
            if last_attempt:
                raise GeminiUnavailableError(f"Gemini request failed: {type(exc).__name__} {exc}") from exc
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue

        if response.status_code in (429, 404):
            raise _ModelUnavailable(gemini_quota.parse_quota_error(response))

        if response.status_code == 503 and not last_attempt:
            logger.warning("Gemini %s overloaded (503), retrying once", model)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue

        if response.status_code != 200:
            logger.warning("Gemini %s returned %d: %s", model, response.status_code, response.text[:300])
            if response.status_code >= 500:
                raise GeminiUnavailableError(f"Gemini returned {response.status_code}: {response.text[:300]}")
            raise GeminiError(f"Gemini returned {response.status_code}: {response.text[:300]}")

        try:
            return _parse_answer(response)
        except GeminiError:
            if last_attempt:
                raise
            logger.warning("Unusable Gemini answer from %s (attempt %d), retrying once", model, attempt)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

    raise AssertionError("unreachable")  # pragma: no cover - loop always returns or raises
