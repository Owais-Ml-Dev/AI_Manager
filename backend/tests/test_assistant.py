"""HTTP tests for the Gemini assistant routes."""

import src.modules.assistant.controller as controller


def test_assistant_health_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        controller,
        "get_assistant_status",
        lambda **kwargs: {
            "provider": "gemini",
            "configured": True,
            "available": True,
            "model": "gemini-test",
        },
    )

    response = client.get("/api/assistant/health")
    assert response.status_code == 200
    assert response.get_json()["data"]["provider"] == "gemini"
    assert response.get_json()["data"]["available"] is True


def test_assistant_chat_requires_body(client):
    assert client.post("/api/assistant/chat").status_code == 400


def test_assistant_chat_requires_nonempty_message(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "   "},
    )
    assert response.status_code == 400


def test_assistant_chat_success(client, monkeypatch):
    monkeypatch.setattr(
        controller,
        "send_chat",
        lambda message, **kwargs: {
            "provider": "gemini",
            "type": "api",
            "model": "gemini-test",
            "reply": "Hello from Gemini.",
        },
    )

    response = client.post(
        "/api/assistant/chat",
        json={"message": "Hello"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["provider"] == "gemini"
    assert data["reply"] == "Hello from Gemini."


def test_assistant_chat_unconfigured_returns_503(client, monkeypatch):
    from src.modules.assistant.providers.base_provider import ProviderNotConfiguredError

    def fail(*args, **kwargs):
        raise ProviderNotConfiguredError("Gemini API key missing.")

    monkeypatch.setattr(controller, "send_chat", fail)
    response = client.post("/api/assistant/chat", json={"message": "Hello"})
    assert response.status_code == 503


def test_assistant_chat_connection_error_returns_502(client, monkeypatch):
    from src.modules.assistant.providers.base_provider import ProviderConnectionError

    def fail(*args, **kwargs):
        raise ProviderConnectionError("Gemini unavailable.")

    monkeypatch.setattr(controller, "send_chat", fail)
    response = client.post("/api/assistant/chat", json={"message": "Hello"})
    assert response.status_code == 502
    assert response.get_json()["retryable"] is True


def test_assistant_chat_rate_limit_returns_429(client, monkeypatch):
    from src.modules.assistant.providers.base_provider import ProviderRateLimitError

    def fail(*args, **kwargs):
        raise ProviderRateLimitError("Gemini is rate limited.")

    monkeypatch.setattr(controller, "send_chat", fail)
    response = client.post("/api/assistant/chat", json={"message": "Hello"})
    assert response.status_code == 429
    data = response.get_json()
    assert data["error_code"] == "provider_rate_limited"
    assert data["retryable"] is True
