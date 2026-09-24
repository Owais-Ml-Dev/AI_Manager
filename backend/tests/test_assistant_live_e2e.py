"""Optional live smoke tests for the real Gemini assistant.

Normal pytest runs skip this file. To run it:

    $env:RUN_LIVE_AI_TESTS="1"
    python -m pytest .\tests\test_assistant_live_e2e.py -v -s

The Flask server must already be running.
"""

import os

import pytest
import requests


BASE_URL = os.getenv(
    "AI_TEST_BASE_URL",
    "http://127.0.0.1:5000",
).rstrip("/")

HTTP_TIMEOUT = int(
    os.getenv(
        "AI_TEST_HTTP_TIMEOUT",
        "120",
    )
)

pytestmark = [
    pytest.mark.live_ai,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_AI_TESTS") != "1",
        reason="Live Gemini tests are disabled.",
    ),
]


def _request(method, path, json_body=None):
    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        json=json_body,
        timeout=HTTP_TIMEOUT,
    )
    body = response.json()
    return response, body


def test_live_gemini_health():
    response, body = _request(
        "GET",
        "/api/assistant/health",
    )

    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["provider"] == "gemini"
    assert body["data"]["configured"] is True
    assert body["data"]["available"] is True


def test_live_gemini_chat():
    response, body = _request(
        "POST",
        "/api/assistant/chat",
        {"message": "Reply only with OK"},
    )

    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["provider"] == "gemini"
    assert body["data"]["reply"].strip()


def test_live_task_command_preview_is_safe():
    response, body = _request(
        "POST",
        "/api/assistant/task-command/preview",
        {
            "message": (
                "Create a recurring test task every weekday at 7 AM "
                "for the next 7 days"
            ),
            "timezone": "+05:30",
        },
    )

    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["provider"] == "gemini"
    data = body["data"]
    assert data["draft_id"]
    assert data["status"] in {"ready", "duplicate_review", "needs_input"}
    if data["command"] is not None:
        assert data["command"]["requires_confirmation"] is True
