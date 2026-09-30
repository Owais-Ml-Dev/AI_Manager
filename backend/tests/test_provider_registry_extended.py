import pytest

pytestmark = pytest.mark.no_db

from src.modules.assistant.providers.provider_factory import (
    create_provider,
)

from src.modules.assistant.providers.provider_registry import (
    provider_is_configured,
    provider_names,
)


def test_extended_provider_registry():
    assert provider_names() == (
        "gemini",
        "groq",
        "cloudflare",
        "openrouter",
        "cerebras",
        "mistral",
        "nvidia",
    )


def test_new_provider_credentials():
    for (
        name,
        field,
    ) in (
        (
            "cerebras",
            "cerebras_api_key",
        ),
        (
            "mistral",
            "mistral_api_key",
        ),
        (
            "nvidia",
            "nvidia_api_key",
        ),
    ):
        assert (
            provider_is_configured(
                name,
                {},
            )
            is False
        )

        assert (
            provider_is_configured(
                name,
                {
                    field: "test-key",
                },
            )
            is True
        )


def test_cerebras_provider_defaults():
    provider = create_provider(
        "cerebras",
        credentials={
            "cerebras_api_key": "x",
        },
    )

    assert (
        provider.base_url
        == "https://api.cerebras.ai/v1"
    )

    assert (
        provider.model
        == "gpt-oss-120b"
    )


def test_mistral_provider_defaults():
    provider = create_provider(
        "mistral",
        credentials={
            "mistral_api_key": "x",
        },
    )

    assert (
        provider.base_url
        == "https://api.mistral.ai/v1"
    )

    assert (
        provider.model
        == "mistral-small-latest"
    )


def test_nvidia_provider_defaults():
    provider = create_provider(
        "nvidia",
        credentials={
            "nvidia_api_key": "x",
        },
    )

    assert (
        provider.base_url
        == "https://integrate.api.nvidia.com/v1"
    )

    assert (
        provider.model
        == "openai/gpt-oss-20b"
    )
