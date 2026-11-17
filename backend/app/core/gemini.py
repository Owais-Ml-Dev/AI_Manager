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


class GeminiError(Exception):
    pass


async def _post_once(prompt: str) -> httpx.Response:
    url = f"{_API_BASE}/{settings.gemini_model}:generateContent"
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                # This model "thinks" before answering (consumes output
                # tokens on hidden reasoning); without headroom that can
                # truncate the actual JSON mid-output. thinkingConfig isn't
                # accepted for this model via this API version, so the fix is
                # just a generous budget rather than disabling thinking.
                "generationConfig": {"maxOutputTokens": 2048},
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
            logger.warning("Gemini request failed (attempt %d): %s", attempt, exc)
            if attempt == _MAX_ATTEMPTS:
                raise GeminiError(f"Gemini request failed: {exc}") from exc
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue

        if response.status_code == 503 and attempt < _MAX_ATTEMPTS:
            logger.warning("Gemini overloaded (503), retrying once")
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        break

    if response.status_code != 200:
        logger.warning("Gemini returned %d: %s", response.status_code, response.text[:300])
        raise GeminiError(f"Gemini returned {response.status_code}: {response.text[:300]}")

    try:
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
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
        logger.warning("Gemini did not return valid JSON: %s", text[:300])
        raise GeminiError(f"Gemini did not return valid JSON: {text[:300]}") from exc
