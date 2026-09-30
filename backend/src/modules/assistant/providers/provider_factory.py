"""
Provider factory facade.

Existing imports can continue using:

    create_provider(...)
    SUPPORTED_PROVIDERS

Internally the implementation now uses the central registry.
"""

from src.modules.assistant.providers.provider_registry import (
    create_registered_provider,
    provider_names,
)


SUPPORTED_PROVIDERS = (
    provider_names()
)


def invalidate_provider_cache(
    name=None,
):
    """
    Backward-compatible no-op.

    Provider instances and request credentials are intentionally
    request scoped.
    """

    return None


def create_provider(
    provider_name="gemini",
    *,
    credentials=None,
    api_key=None,
):
    normalized = str(
        provider_name
        or "gemini"
    ).strip().lower()

    values = dict(
        credentials
        or {}
    )

    # Compatibility with older Gemini-only callers/tests.
    if (
        api_key
        and not values.get(
            "gemini_api_key"
        )
    ):
        values[
            "gemini_api_key"
        ] = api_key

    return (
        create_registered_provider(
            normalized,
            values,
        )
    )
