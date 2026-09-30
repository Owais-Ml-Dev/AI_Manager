"""
Central registry for AI providers.

The rest of the assistant should not need provider-specific
if/else chains.

Adding another provider later should mainly mean:

1. Create the provider class.
2. Add one ProviderSpec here.
3. Add its credential header/storage support in Flutter.

Routing logic remains unchanged.
"""

from dataclasses import dataclass

from src.modules.assistant.providers.cloudflare_provider import (
    CloudflareProvider,
)
from src.modules.assistant.providers.gemini_provider import (
    GeminiProvider,
)
from src.modules.assistant.providers.groq_provider import (
    GroqProvider,
)
from src.modules.assistant.providers.openrouter_provider import (
    OpenRouterProvider,
)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    credential_fields: tuple
    factory: object

    def configured(
        self,
        credentials,
    ):
        return all(
            bool(
                str(
                    credentials.get(
                        field,
                        "",
                    )
                    or ""
                ).strip()
            )
            for field in self.credential_fields
        )

    def create(
        self,
        credentials,
    ):
        return self.factory(
            credentials
        )


def _gemini_factory(
    credentials,
):
    return GeminiProvider(
        api_key=credentials.get(
            "gemini_api_key",
        ),
    )


def _groq_factory(
    credentials,
):
    return GroqProvider(
        api_key=credentials.get(
            "groq_api_key",
        ),
    )


def _cloudflare_factory(
    credentials,
):
    return CloudflareProvider(
        api_key=credentials.get(
            "cloudflare_api_token",
        ),
        account_id=credentials.get(
            "cloudflare_account_id",
        ),
    )


def _openrouter_factory(
    credentials,
):
    return OpenRouterProvider(
        api_key=credentials.get(
            "openrouter_api_key",
        ),
    )


_PROVIDER_REGISTRY = {
    "gemini": ProviderSpec(
        name="gemini",
        label="Gemini",
        credential_fields=(
            "gemini_api_key",
        ),
        factory=_gemini_factory,
    ),

    "groq": ProviderSpec(
        name="groq",
        label="Groq",
        credential_fields=(
            "groq_api_key",
        ),
        factory=_groq_factory,
    ),

    "cloudflare": ProviderSpec(
        name="cloudflare",
        label="Cloudflare Workers AI",
        credential_fields=(
            "cloudflare_api_token",
            "cloudflare_account_id",
        ),
        factory=_cloudflare_factory,
    ),

    "openrouter": ProviderSpec(
        name="openrouter",
        label="OpenRouter",
        credential_fields=(
            "openrouter_api_key",
        ),
        factory=_openrouter_factory,
    ),
}


def provider_names():
    return tuple(
        _PROVIDER_REGISTRY.keys()
    )


def provider_specs():
    return tuple(
        _PROVIDER_REGISTRY.values()
    )


def get_provider_spec(
    name,
):
    normalized = str(
        name or ""
    ).strip().lower()

    try:
        return _PROVIDER_REGISTRY[
            normalized
        ]
    except KeyError as error:
        raise ValueError(
            "Unsupported AI provider: "
            f"{normalized or name}"
        ) from error


def provider_is_configured(
    name,
    credentials,
):
    return get_provider_spec(
        name
    ).configured(
        credentials
    )


def create_registered_provider(
    name,
    credentials,
):
    return get_provider_spec(
        name
    ).create(
        credentials
    )


def provider_metadata():
    return [
        {
            "name": spec.name,
            "label": spec.label,
            "credential_fields": list(
                spec.credential_fields
            ),
        }
        for spec in provider_specs()
    ]
