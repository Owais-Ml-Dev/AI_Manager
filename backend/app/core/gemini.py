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

import httpx

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
    """Gemini is down, overloaded or too slow (timeout, network, 429, 5xx) —
    worth telling the user to try again, unlike a GeminiError."""


async def _post_once(prompt: str) -> httpx.Response:
    url = f"{_API_BASE}/{settings.gemini_model}:generateContent"
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
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


async def generate_json(prompt: str) -> dict:
    """Sends `prompt` to Gemini and parses its response as JSON.

    Raises GeminiError on any failure (HTTP error, non-JSON response, Gemini
    unavailable) — callers must treat Gemini's output as untrusted and are
    expected to handle this by falling back to a clarification message. Every
    failure is logged here first, since callers degrade to a generic message
    that would otherwise hide the real cause.
    """
    response = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await _post_once(prompt)
        except httpx.HTTPError as exc:
            logger.warning("Gemini request failed (attempt %d): %s %s", attempt, type(exc).__name__, exc)
            if attempt == _MAX_ATTEMPTS:
                raise GeminiUnavailableError(f"Gemini request failed: {type(exc).__name__} {exc}") from exc
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue

        if response.status_code == 503 and attempt < _MAX_ATTEMPTS:
            logger.warning("Gemini overloaded (503), retrying once")
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        break

    if response.status_code != 200:
        logger.warning("Gemini returned %d: %s", response.status_code, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            raise GeminiUnavailableError(f"Gemini returned {response.status_code}: {response.text[:300]}")
        raise GeminiError(f"Gemini returned {response.status_code}: {response.text[:300]}")

    try:
        data = response.json()
        candidate = data["candidates"][0]
        # An answer can arrive split across several parts; read them all.
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Unexpected Gemini response shape: %s — body: %s", exc, response.text[:300])
        raise GeminiError(f"Unexpected Gemini response shape: {exc}") from exc
    finish_reason = candidate.get("finishReason")

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # finishReason says WHY it stopped (e.g. MAX_TOKENS, SAFETY) — the
        # missing clue for the rare cut-off answers seen in testing.
        logger.warning("Gemini did not return valid JSON (finishReason=%s, model=%s): %s",
                       finish_reason, data.get("modelVersion"), text[:300])
        raise GeminiError(f"Gemini did not return valid JSON: {text[:300]}") from exc
