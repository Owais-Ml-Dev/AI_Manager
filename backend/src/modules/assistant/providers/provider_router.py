"""
Embedded multi-provider AI router.

This gives the Flask application FreeLLMAPI-style routing
without running a separate service.

Current default priority:

    Gemini
      -> Groq
      -> Cloudflare Workers AI
      -> OpenRouter

The router is provider-agnostic. Provider-specific construction
and required credentials live in provider_registry.py.
"""

import os

from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)

from src.modules.assistant.providers.cooldown_manager import (
    provider_cooldowns,
)

from src.modules.assistant.providers.provider_factory import (
    SUPPORTED_PROVIDERS,
    create_provider,
)

from src.modules.assistant.providers.provider_registry import (
    provider_is_configured,
)


DEFAULT_PROVIDER_PRIORITY = (
    "gemini",
    "groq",
    "cloudflare",
    "openrouter",
    "cerebras",
    "mistral",
    "nvidia",
)


def _priority():
    raw = os.getenv(
        "AI_PROVIDER_PRIORITY",
        ",".join(
            DEFAULT_PROVIDER_PRIORITY
        ),
    )

    values = []

    for item in raw.split(","):
        name = (
            item
            .strip()
            .lower()
        )

        if (
            name
            and name in SUPPORTED_PROVIDERS
            and name not in values
        ):
            values.append(
                name
            )

    # Ensure newly registered providers are not accidentally
    # unreachable merely because an older .env priority exists.
    for name in SUPPORTED_PROVIDERS:
        if name not in values:
            values.append(
                name
            )

    return tuple(
        values
    )


def _merge_credentials(
    credentials=None,
    api_key=None,
):
    values = dict(
        credentials
        or {}
    )

    if (
        api_key
        and not values.get(
            "gemini_api_key"
        )
    ):
        values[
            "gemini_api_key"
        ] = api_key

    return values


def _auto_fallback_enabled(
    credentials,
):
    value = credentials.get(
        "auto_fallback",
        True,
    )

    if isinstance(
        value,
        bool,
    ):
        return value

    return (
        str(
            value
        )
        .strip()
        .lower()
        not in {
            "false",
            "0",
            "off",
            "no",
        }
    )


def _candidate_names(
    credentials,
):
    priority = list(
        _priority()
    )

    preferred = str(
        credentials.get(
            "preferred_provider",
            "",
        )
        or ""
    ).strip().lower()

    # Put the user's selected provider first.
    if (
        preferred
        and preferred
        in SUPPORTED_PROVIDERS
    ):
        priority = [
            preferred,
            *[
                name
                for name in priority
                if name != preferred
            ],
        ]

    configured = [
        name
        for name in priority
        if provider_is_configured(
            name,
            credentials,
        )
    ]

    if not configured:
        return []

    if not _auto_fallback_enabled(
        credentials
    ):
        # Fallback OFF means:
        #
        # use exactly the selected primary provider.
        #
        # If its key is no longer configured, return no
        # candidates instead of silently changing provider.
        if preferred:
            if preferred in configured:
                return [
                    preferred,
                ]

            return []

        return configured[:1]

    return configured


def _cooldown_seconds(
    error,
):
    if isinstance(
        error,
        ProviderRateLimitError,
    ):
        retry_after = getattr(
            error,
            "retry_after_seconds",
            None,
        )

        if retry_after:
            return max(
                1.0,
                float(
                    retry_after
                ),
            )

        return float(
            os.getenv(
                "AI_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS",
                "120",
            )
        )

    if isinstance(
        error,
        ProviderNotConfiguredError,
    ):
        return float(
            os.getenv(
                "AI_PROVIDER_AUTH_COOLDOWN_SECONDS",
                "300",
            )
        )

    return float(
        os.getenv(
            "AI_PROVIDER_ERROR_COOLDOWN_SECONDS",
            "20",
        )
    )


def _failure_reason(
    error,
):
    if isinstance(
        error,
        ProviderRateLimitError,
    ):
        return "rate_limited"

    if isinstance(
        error,
        ProviderNotConfiguredError,
    ):
        return "not_configured"

    if isinstance(
        error,
        ProviderConnectionError,
    ):
        return "temporarily_unavailable"

    if isinstance(
        error,
        ProviderResponseError,
    ):
        return "invalid_response"

    return "provider_error"


def _mark_failure(
    name,
    error,
):
    provider_cooldowns.set(
        name,
        _cooldown_seconds(
            error
        ),
        reason=_failure_reason(
            error
        ),
    )


def _mark_success(
    name,
):
    # Successful recovery should immediately remove stale
    # cooldown state.
    provider_cooldowns.clear(
        name
    )


def _run(
    method_name,
    *,
    credentials=None,
    api_key=None,
    **kwargs,
):
    credentials = (
        _merge_credentials(
            credentials,
            api_key,
        )
    )

    candidates = (
        _candidate_names(
            credentials
        )
    )

    if not candidates:
        raise (
            ProviderNotConfiguredError(
                "Add at least one AI provider API key in Settings."
            )
        )

    attempted = []
    errors = []

    first_provider = (
        candidates[0]
    )

    # Pass 1:
    # skip temporarily cooled-down providers.
    #
    # Pass 2:
    # if every configured provider was cooling down, allow one
    # normal pass so the app can recover without a restart.
    for allow_cooldown in (
        False,
        True,
    ):
        for name in candidates:

            if name in attempted:
                continue

            if (
                not allow_cooldown
                and provider_cooldowns.active(
                    name
                )
            ):
                continue

            attempted.append(
                name
            )

            provider = (
                create_provider(
                    name,
                    credentials=credentials,
                )
            )

            try:
                result = getattr(
                    provider,
                    method_name,
                )(
                    **kwargs
                )

                _mark_success(
                    name
                )

                return {
                    "provider": name,

                    "type": getattr(
                        provider,
                        "provider_type",
                        "api",
                    ),

                    "model": getattr(
                        provider,
                        "model_used",
                        getattr(
                            provider,
                            "model",
                            "",
                        ),
                    ),

                    "result": result,

                    "fallback_used": (
                        name
                        != first_provider
                    ),

                    "attempted_providers": (
                        list(
                            attempted
                        )
                    ),

                    "cooldowns": (
                        provider_cooldowns.snapshot()
                    ),
                }

            except (
                ProviderNotConfiguredError,
                ProviderRateLimitError,
                ProviderConnectionError,
                ProviderResponseError,
            ) as error:

                errors.append(
                    (
                        name,
                        error,
                    )
                )

                _mark_failure(
                    name,
                    error,
                )

                print(
                    "[assistant] "
                    f"{name} unavailable "
                    f"({_failure_reason(error)}): "
                    f"{error}",
                    flush=True,
                )

                # Auto fallback OFF means exactly one provider.
                if not _auto_fallback_enabled(
                    credentials
                ):
                    raise

    if errors:
        raise (
            errors[-1][1]
        )

    raise ProviderConnectionError(
        "No AI provider was available."
    )


def chat_with_fallback(
    message,
    system_prompt,
    *,
    credentials=None,
    api_key=None,
):
    return _run(
        "chat",
        credentials=credentials,
        api_key=api_key,
        message=message,
        system_prompt=system_prompt,
    )


def structured_json_with_fallback(
    message,
    system_prompt,
    response_schema,
    *,
    credentials=None,
    api_key=None,
):
    return _run(
        "structured_json",
        credentials=credentials,
        api_key=api_key,
        message=message,
        system_prompt=system_prompt,
        response_schema=response_schema,
    )


def provider_health(
    provider_name,
    *,
    credentials=None,
    api_key=None,
):
    credentials = (
        _merge_credentials(
            credentials,
            api_key,
        )
    )

    provider = (
        create_provider(
            provider_name,
            credentials=credentials,
            api_key=api_key,
        )
    )

    health = (
        provider.health()
    )

    health[
        "cooldown_active"
    ] = (
        provider_cooldowns.active(
            provider_name
        )
    )

    health[
        "cooldown_remaining_seconds"
    ] = round(
        provider_cooldowns.remaining(
            provider_name
        ),
        1,
    )

    return health


def router_status(
    *,
    credentials=None,
    api_key=None,
):
    credentials = (
        _merge_credentials(
            credentials,
            api_key,
        )
    )

    configured = [
        name
        for name in _priority()
        if provider_is_configured(
            name,
            credentials,
        )
    ]

    return {
        "priority": list(
            _priority()
        ),

        "configured_providers": (
            configured
        ),

        "auto_fallback": (
            _auto_fallback_enabled(
                credentials
            )
        ),

        "cooldowns": (
            provider_cooldowns.snapshot()
        ),
    }
