"""Tests for authoritative provider/model identity replies."""

import src.modules.assistant.service as service


def _routed(**overrides):
    value = {
        "provider": "groq",
        "type": "api",
        "model": "openai/gpt-oss-20b",
        "result": "I am definitely some other model.",
        "fallback_used": False,
        "attempted_providers": ["groq"],
    }
    value.update(overrides)
    return value


def test_identity_question_uses_backend_metadata(monkeypatch):
    monkeypatch.setattr(
        service,
        "chat_with_fallback",
        lambda **kwargs: _routed(),
    )

    result = service.send_chat("Which AI is this?")

    assert result["provider"] == "groq"
    assert result["model"] == "openai/gpt-oss-20b"
    assert result["fallback_used"] is False
    assert "Provider: Groq" in result["reply"]
    assert "Model: openai/gpt-oss-20b" in result["reply"]
    assert "Fallback: No" in result["reply"]
    assert "some other model" not in result["reply"]


def test_identity_question_reports_actual_fallback_route(monkeypatch):
    monkeypatch.setattr(
        service,
        "chat_with_fallback",
        lambda **kwargs: _routed(
            provider="cloudflare",
            model="@cf/openai/gpt-oss-20b",
            fallback_used=True,
            attempted_providers=["groq", "gemini", "cloudflare"],
        ),
    )

    result = service.send_chat("What model are you using?")

    assert "Provider: Cloudflare Workers AI" in result["reply"]
    assert "Model: @cf/openai/gpt-oss-20b" in result["reply"]
    assert "Fallback: Yes" in result["reply"]
    assert "Route: Groq -> Gemini -> Cloudflare Workers AI" in result["reply"]


def test_direct_provider_question_is_detected(monkeypatch):
    monkeypatch.setattr(
        service,
        "chat_with_fallback",
        lambda **kwargs: _routed(),
    )

    result = service.send_chat("Are you Gemini?")

    assert "Provider: Groq" in result["reply"]
    assert "Model: openai/gpt-oss-20b" in result["reply"]


def test_normal_chat_keeps_model_generated_reply(monkeypatch):
    monkeypatch.setattr(
        service,
        "chat_with_fallback",
        lambda **kwargs: _routed(result="Normal assistant answer."),
    )

    result = service.send_chat("Explain recurring tasks")

    assert result["reply"] == "Normal assistant answer."


def test_model_recommendation_question_is_not_identity_query():
    assert service._is_runtime_identity_question(
        "What model should I use for image classification?"
    ) is False
