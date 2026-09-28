"""Short-lived Gemini Live API credentials."""

import requests

from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderResponseError,
)


LIVE_MODEL = "gemini-3.8-live"

TOKEN_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/auth_tokens"
)


def create_live_token(api_key):
    key = str(api_key or "").strip()

    if not key:
        raise ProviderNotConfiguredError(
            "Add your Gemini API key in Settings first."
        )

    try:
        response = requests.post(
            TOKEN_URL,
            headers={
                "x-goog-api-key": key,
                "Content-Type": "application/json",
            },
            json={
                "uses": 1,
            },
            timeout=15,
        )

    except requests.RequestException as error:
        raise ProviderConnectionError(
            "Could not reach Gemini Live API."
        ) from error

    if not response.ok:
        try:
            payload = response.json()

            message = (
                payload.get(
                    "error",
                    {},
                ).get(
                    "message"
                )
            )
        except Exception:
            message = None

        raise ProviderResponseError(
            message
            or (
                "Gemini Live token request failed "
                f"(HTTP {response.status_code})."
            )
        )

    try:
        payload = response.json()

        token = str(
            payload.get("name")
            or ""
        ).strip()

    except Exception as error:
        raise ProviderResponseError(
            "Gemini returned an invalid Live token."
        ) from error

    if not token:
        raise ProviderResponseError(
            "Gemini did not return a Live token."
        )

    return {
        "token": token,
        "model": LIVE_MODEL,
    }
