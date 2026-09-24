"""Unit tests for the Gemini adapter."""


import pytest


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        json_data=None,
    ):
        self.status_code = status_code
        self._json_data = (
            json_data
            if json_data is not None
            else {}
        )

    @property
    def ok(self):
        return (
            200
            <= self.status_code
            < 300
        )

    def json(self):
        return self._json_data


def _configure_gemini(
    monkeypatch,
):
    from src.modules.assistant.providers import (
        gemini_provider,
    )

    monkeypatch.setenv(
        "GEMINI_MAX_RETRIES",
        "0",
    )

    return gemini_provider


def test_gemini_chat(
    monkeypatch,
):
    gemini_provider = (
        _configure_gemini(
            monkeypatch,
        )
    )

    monkeypatch.setattr(
        gemini_provider._GEMINI_HTTP_SESSION,
        "post",
        lambda *args, **kwargs:
            FakeResponse(
                json_data={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text":
                                            "Gemini answer"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ),
    )

    provider = (
        gemini_provider.GeminiProvider(
            api_key="test-key",
        )
    )

    assert (
        provider.chat(
            "Hello",
            "System",
        )
        == "Gemini answer"
    )


def test_gemini_without_api_key():
    from src.modules.assistant.providers import (
        gemini_provider,
    )

    from src.modules.assistant.providers.base_provider import (
        ProviderNotConfiguredError,
    )

    provider = (
        gemini_provider.GeminiProvider()
    )

    with pytest.raises(
        ProviderNotConfiguredError
    ):
        provider.chat(
            "Hello",
            "System",
        )


def test_gemini_rate_limit(
    monkeypatch,
):
    gemini_provider = (
        _configure_gemini(
            monkeypatch,
        )
    )

    from src.modules.assistant.providers.base_provider import (
        ProviderRateLimitError,
    )

    monkeypatch.setattr(
        gemini_provider._GEMINI_HTTP_SESSION,
        "post",
        lambda *args, **kwargs:
            FakeResponse(
                status_code=429,
            ),
    )

    provider = (
        gemini_provider.GeminiProvider(
            api_key="test-key",
        )
    )

    with pytest.raises(
        ProviderRateLimitError
    ):
        provider.chat(
            "Hello",
            "System",
        )


def test_gemini_structured_json_uses_response_schema(monkeypatch):
    gemini_provider = _configure_gemini(monkeypatch)
    captured = {}

    def fake_post(*args, **kwargs):
        captured.update(kwargs.get("json") or {})
        return FakeResponse(
            json_data={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"action":"list_active_tasks",'
                                        '"arguments":{}}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        gemini_provider._GEMINI_HTTP_SESSION,
        "post",
        fake_post,
    )

    provider = gemini_provider.GeminiProvider(api_key="test-key")
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "arguments": {"type": "object"},
        },
        "required": ["action", "arguments"],
    }

    result = provider.structured_json(
        "List my tasks",
        "Return JSON",
        schema,
    )

    assert result["action"] == "list_active_tasks"
    config = captured["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"] == schema
