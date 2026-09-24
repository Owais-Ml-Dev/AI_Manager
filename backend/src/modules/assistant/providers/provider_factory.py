"""Gemini provider construction."""


from src.modules.assistant.providers.gemini_provider import (
    GeminiProvider,
)


def invalidate_provider_cache(name=None):
    """Backward-compatible no-op."""
    return None


def create_provider(
    api_key=None,
):
    """
    Create Gemini for one request.

    The API key is not cached or persisted here.
    """
    return GeminiProvider(
        api_key=api_key,
    )
