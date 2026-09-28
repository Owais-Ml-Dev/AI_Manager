"""Automatic multi-provider fallback router.

Priority:
    Gemini -> Groq -> Cloudflare Workers AI -> OpenRouter Free

A provider that is temporarily rate-limited is cooled down for a short period
so the next request moves immediately to the next configured provider.
"""

import os
import time

from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.modules.assistant.providers.provider_factory import create_provider


DEFAULT_PROVIDER_PRIORITY = (
    "gemini",
    "groq",
    "cloudflare",
    "openrouter",
)

_cooldowns = {}


def _priority():
    configured = [
        value.strip().lower()
        for value in os.getenv(
            "AI_PROVIDER_PRIORITY",
            ",".join(DEFAULT_PROVIDER_PRIORITY),
        ).split(",")
        if value.strip()
    ]
    return tuple(configured or DEFAULT_PROVIDER_PRIORITY)


def _merge_credentials(credentials=None, api_key=None):
    value = dict(credentials or {})
    if api_key and not value.get("gemini_api_key"):
        value["gemini_api_key"] = api_key
    return value


def _has_credentials(name, credentials):
    if name == "gemini":
        return bool(credentials.get("gemini_api_key"))
    if name == "groq":
        return bool(credentials.get("groq_api_key"))
    if name == "cloudflare":
        return bool(
            credentials.get("cloudflare_api_token")
            and credentials.get("cloudflare_account_id")
        )
    if name == "openrouter":
        return bool(credentials.get("openrouter_api_key"))
    return False


def _cooldown_active(name):
    until = _cooldowns.get(name, 0)
    if until <= time.monotonic():
        _cooldowns.pop(name, None)
        return False
    return True


def _mark_failure(name, error):
    if isinstance(error, ProviderRateLimitError):
        delay = getattr(error, "retry_after_seconds", None)
        if not delay:
            delay = float(os.getenv("AI_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS", "120"))
    elif isinstance(error, ProviderNotConfiguredError):
        delay = float(os.getenv("AI_PROVIDER_AUTH_COOLDOWN_SECONDS", "300"))
    else:
        delay = float(os.getenv("AI_PROVIDER_ERROR_COOLDOWN_SECONDS", "20"))
    _cooldowns[name] = time.monotonic() + max(1.0, float(delay))


def _candidate_names(credentials):
    priority = _priority()
    configured = [name for name in priority if _has_credentials(name, credentials)]
    return configured


def _run(method_name, *, credentials=None, api_key=None, **kwargs):
    credentials = _merge_credentials(credentials, api_key)
    candidates = _candidate_names(credentials)
    if not candidates:
        raise ProviderNotConfiguredError(
            "Add at least one AI provider API key in Settings."
        )

    attempted = []
    errors = []
    first = candidates[0]

    # Try providers not in cooldown first. If every configured provider is in
    # cooldown, do a normal pass anyway so recovery does not require a restart.
    passes = [False, True]
    for allow_cooldown in passes:
        for name in candidates:
            if name in attempted:
                continue
            if not allow_cooldown and _cooldown_active(name):
                continue

            attempted.append(name)
            provider = create_provider(name, credentials=credentials)
            try:
                result = getattr(provider, method_name)(**kwargs)
                return {
                    "provider": name,
                    "type": getattr(provider, "provider_type", "api"),
                    "model": getattr(provider, "model_used", provider.model),
                    "result": result,
                    "fallback_used": name != first,
                    "attempted_providers": list(attempted),
                }
            except (
                ProviderNotConfiguredError,
                ProviderRateLimitError,
                ProviderConnectionError,
                ProviderResponseError,
            ) as error:
                errors.append((name, error))
                _mark_failure(name, error)
                print(
                    f"[assistant] {name} unavailable ({error}); trying fallback.",
                    flush=True,
                )

    if errors:
        raise errors[-1][1]
    raise ProviderConnectionError("No AI provider was available.")


def chat_with_fallback(message, system_prompt, *, credentials=None, api_key=None):
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


def provider_health(provider_name, *, credentials=None, api_key=None):
    credentials = _merge_credentials(credentials, api_key)
    provider = create_provider(
        provider_name,
        credentials=credentials,
        api_key=api_key,
    )
    return provider.health()
