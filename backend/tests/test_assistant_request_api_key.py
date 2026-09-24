"""Request-scoped Gemini API-key header tests."""


import src.modules.assistant.controller as controller


def test_chat_passes_user_api_key(
    client,
    monkeypatch,
):
    captured = {}

    def fake_send_chat(
        message,
        api_key=None,
    ):
        captured["api_key"] = (
            api_key
        )

        return {
            "provider": "gemini",
            "type": "api",
            "model": "gemini-test",
            "reply": "OK",
        }

    monkeypatch.setattr(
        controller,
        "send_chat",
        fake_send_chat,
    )

    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "Hello",
        },
        headers={
            "X-Gemini-Api-Key":
                "users-private-key",
        },
    )

    assert response.status_code == 200

    assert (
        captured["api_key"]
        == "users-private-key"
    )


def test_health_passes_user_api_key(
    client,
    monkeypatch,
):
    captured = {}

    def fake_health(
        api_key=None,
    ):
        captured["api_key"] = (
            api_key
        )

        return {
            "provider": "gemini",
            "configured": True,
            "available": True,
        }

    monkeypatch.setattr(
        controller,
        "get_assistant_status",
        fake_health,
    )

    response = client.get(
        "/api/assistant/health",
        headers={
            "X-Gemini-Api-Key":
                "users-private-key",
        },
    )

    assert response.status_code == 200

    assert (
        captured["api_key"]
        == "users-private-key"
    )
