import pytest

pytestmark = pytest.mark.no_db

from src.modules.assistant.providers import (
    provider_router,
)

from src.modules.assistant.providers.base_provider import (
    ProviderRateLimitError,
)

from src.modules.assistant.providers.cooldown_manager import (
    ProviderCooldownManager,
)

from src.modules.assistant.providers.provider_registry import (
    provider_is_configured,
    provider_names,
)


def test_registry_contains_current_providers():
    assert provider_names() == (
        "gemini",
        "groq",
        "cloudflare",
        "openrouter",
        "cerebras",
        "mistral",
        "nvidia",
    )


def test_cloudflare_requires_token_and_account_id():
    assert (
        provider_is_configured(
            "cloudflare",
            {
                "cloudflare_api_token": (
                    "token"
                ),
            },
        )
        is False
    )

    assert (
        provider_is_configured(
            "cloudflare",
            {
                "cloudflare_api_token": (
                    "token"
                ),
                "cloudflare_account_id": (
                    "account"
                ),
            },
        )
        is True
    )


def test_candidate_priority():
    credentials = {
        "gemini_api_key": "g",
        "groq_api_key": "q",
        "openrouter_api_key": "o",
        "auto_fallback": True,
    }

    assert (
        provider_router._candidate_names(
            credentials
        )
        == [
            "gemini",
            "groq",
            "openrouter",
        ]
    )


def test_auto_fallback_off_uses_only_first():
    credentials = {
        "gemini_api_key": "g",
        "groq_api_key": "q",
        "openrouter_api_key": "o",
        "auto_fallback": False,
    }

    assert (
        provider_router._candidate_names(
            credentials
        )
        == [
            "gemini",
        ]
    )


def test_cooldown_manager():
    now = [
        100.0
    ]

    manager = (
        ProviderCooldownManager(
            clock=lambda: now[0]
        )
    )

    manager.set(
        "gemini",
        30,
        reason="rate_limited",
    )

    assert (
        manager.active(
            "gemini"
        )
        is True
    )

    assert (
        manager.remaining(
            "gemini"
        )
        == pytest.approx(
            30.0
        )
    )

    now[0] = 131.0

    assert (
        manager.active(
            "gemini"
        )
        is False
    )


class FakeProvider:
    provider_type = "api"

    def __init__(
        self,
        name,
        *,
        result=None,
        error=None,
    ):
        self.provider_name = name
        self.model = (
            f"{name}-test"
        )
        self.model_used = (
            self.model
        )
        self._result = result
        self._error = error

    def chat(
        self,
        message,
        system_prompt,
    ):
        if self._error:
            raise self._error

        return self._result


def test_rate_limit_falls_back(
    monkeypatch,
):
    gemini = FakeProvider(
        "gemini",
        error=(
            ProviderRateLimitError(
                "limited"
            )
        ),
    )

    groq = FakeProvider(
        "groq",
        result="groq worked",
    )

    providers = {
        "gemini": gemini,
        "groq": groq,
    }

    monkeypatch.setattr(
        provider_router,
        "create_provider",
        lambda name, **kwargs: (
            providers[name]
        ),
    )

    provider_router.provider_cooldowns.clear()

    result = (
        provider_router.chat_with_fallback(
            "hello",
            "system",
            credentials={
                "gemini_api_key": "g",
                "groq_api_key": "q",
                "auto_fallback": True,
            },
        )
    )

    assert (
        result["provider"]
        == "groq"
    )

    assert (
        result["fallback_used"]
        is True
    )

    assert (
        result[
            "attempted_providers"
        ]
        == [
            "gemini",
            "groq",
        ]
    )


def test_auto_fallback_off_does_not_try_groq(
    monkeypatch,
):
    calls = []

    gemini = FakeProvider(
        "gemini",
        error=(
            ProviderRateLimitError(
                "limited"
            )
        ),
    )

    groq = FakeProvider(
        "groq",
        result="should not run",
    )

    providers = {
        "gemini": gemini,
        "groq": groq,
    }

    def fake_create(
        name,
        **kwargs,
    ):
        calls.append(
            name
        )

        return providers[
            name
        ]

    monkeypatch.setattr(
        provider_router,
        "create_provider",
        fake_create,
    )

    provider_router.provider_cooldowns.clear()

    with pytest.raises(
        ProviderRateLimitError
    ):
        provider_router.chat_with_fallback(
            "hello",
            "system",
            credentials={
                "gemini_api_key": "g",
                "groq_api_key": "q",
                "auto_fallback": False,
            },
        )

    assert calls == [
        "gemini",
    ]
