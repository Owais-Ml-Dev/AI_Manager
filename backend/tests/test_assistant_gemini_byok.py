"""Request-scoped Gemini API-key tests."""


def test_request_key_is_used(
    monkeypatch,
):
    from src.modules.assistant.providers import (
        gemini_provider,
    )

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "backend-key-must-not-be-used",
    )

    provider = (
        gemini_provider.GeminiProvider(
            api_key="users-own-key",
        )
    )

    assert (
        provider.api_key
        == "users-own-key"
    )

    assert (
        provider.credential_source
        == "request"
    )


def test_environment_key_is_ignored(
    monkeypatch,
):
    from src.modules.assistant.providers import (
        gemini_provider,
    )

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "backend-key-must-not-be-used",
    )

    provider = (
        gemini_provider.GeminiProvider()
    )

    assert provider.api_key == ""

    assert (
        provider.credential_source
        is None
    )


def test_users_get_separate_providers():
    from src.modules.assistant.providers.provider_factory import (
        create_provider,
    )

    first = create_provider(
        api_key="first-user-key",
    )

    second = create_provider(
        api_key="second-user-key",
    )

    assert first is not second

    assert (
        first.api_key
        == "first-user-key"
    )

    assert (
        second.api_key
        == "second-user-key"
    )
