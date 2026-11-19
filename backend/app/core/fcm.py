"""Firebase Cloud Messaging (HTTP v1) client: sends a push to one device.

Auth without extra libraries: a Google service account signs a short JWT
(RS256, via PyJWT + cryptography, already dependencies) which Google's token
endpoint exchanges for a 1-hour OAuth access token. The token is cached and
refreshed 5 minutes before it expires.

Configuration: FIREBASE_CREDENTIALS_FILE = path to the service-account JSON
downloaded from Firebase (a private key — kept in backend/secrets/, which is
gitignored). Without it, push is simply off: reminders still land in the
in-app inbox.

Android delivery choices (the app must create a notification channel with
the same id):
- priority HIGH: reminders are time-sensitive; normal priority can be held
  back for a long time by Android's battery saver (Doze).
- ttl 1 hour: matches the worker's rule that reminders over an hour late are
  stale — a phone that was off doesn't get yesterday's "do X at 7am".
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger("fcm")

ANDROID_CHANNEL_ID = "task_reminders"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_TIMEOUT_SECONDS = 10.0
_TTL = "3600s"


@dataclass
class SendResult:
    outcome: str        # "sent" | "invalid_token" | "retryable" | "error"
    detail: str = ""


class FcmConfigError(Exception):
    """Credentials missing/unreadable or rejected by Google."""


class _Credentials:
    def __init__(self, data: dict):
        try:
            self.project_id: str = data["project_id"]
            self.client_email: str = data["client_email"]
            self.private_key: str = data["private_key"]
            self.token_uri: str = data.get("token_uri", "https://oauth2.googleapis.com/token")
        except KeyError as exc:
            raise FcmConfigError(f"service-account JSON is missing {exc}") from exc


_credentials: _Credentials | None = None
_access_token: str | None = None
_token_expires_at = 0.0
_token_lock = asyncio.Lock()


def is_configured() -> bool:
    return bool(settings.firebase_credentials_file)


def _load_credentials() -> _Credentials:
    global _credentials
    if _credentials is None:
        path = Path(settings.firebase_credentials_file)
        if not path.is_absolute():  # relative paths are relative to the backend folder
            path = Path(__file__).resolve().parents[2] / path
        try:
            _credentials = _Credentials(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise FcmConfigError(f"cannot read FIREBASE_CREDENTIALS_FILE ({path.name}): {exc}") from exc
    return _credentials


def build_assertion(creds: _Credentials, now: float | None = None) -> str:
    """The signed JWT Google exchanges for an access token."""
    issued = int(now if now is not None else time.time())
    claims = {"iss": creds.client_email, "scope": _SCOPE, "aud": creds.token_uri,
              "iat": issued, "exp": issued + 3600}
    return jwt.encode(claims, creds.private_key, algorithm="RS256")


async def _get_access_token(client: httpx.AsyncClient) -> str:
    global _access_token, _token_expires_at
    async with _token_lock:
        if _access_token and time.time() < _token_expires_at - 300:
            return _access_token
        creds = _load_credentials()
        response = await client.post(creds.token_uri, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": build_assertion(creds),
        })
        if response.status_code != 200:
            raise FcmConfigError(f"Google rejected the service account ({response.status_code}): {response.text[:200]}")
        body = response.json()
        _access_token = body["access_token"]
        _token_expires_at = time.time() + int(body.get("expires_in", 3600))
        return _access_token


def build_message(token: str, title: str, body: str, data: dict[str, str]) -> dict:
    return {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": data,  # FCM requires string values
            "android": {
                "priority": "HIGH",
                "ttl": _TTL,
                "notification": {"channel_id": ANDROID_CHANNEL_ID, "tag": data.get("task_id", "")},
            },
        }
    }


def classify(response: httpx.Response) -> SendResult:
    """Maps FCM's answer to what the caller should do."""
    if response.status_code == 200:
        return SendResult("sent")
    text = response.text[:300]
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    codes = {d.get("errorCode") for d in error.get("details", []) if isinstance(d, dict)}
    status = error.get("status", "")
    # The device token is no longer valid (app uninstalled, token rotated).
    if "UNREGISTERED" in codes or status == "NOT_FOUND" or (
        status == "INVALID_ARGUMENT" and "registration token" in error.get("message", "").lower()
    ):
        return SendResult("invalid_token", text)
    if response.status_code == 429 or response.status_code >= 500 or "QUOTA_EXCEEDED" in codes:
        return SendResult("retryable", text)
    return SendResult("error", text)  # e.g. 401/403: credentials or project misconfigured


async def send(token: str, title: str, body: str, data: dict[str, str], validate_only: bool = False) -> SendResult:
    """Sends one push. Never raises for FCM-side outcomes (they're in the
    result); raises FcmConfigError if credentials are missing/rejected."""
    payload = build_message(token, title, body, data)
    if validate_only:
        payload["validate_only"] = True
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        access_token = await _get_access_token(client)
        try:
            response = await client.post(
                _SEND_URL.format(project=_load_credentials().project_id),
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            return SendResult("retryable", f"{type(exc).__name__}: {exc}")
    result = classify(response)
    if result.outcome == "error":
        logger.warning("FCM send failed: %s", result.detail)
    return result
