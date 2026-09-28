"""Construct one AI provider instance for one request."""

from src.modules.assistant.providers.cloudflare_provider import CloudflareProvider
from src.modules.assistant.providers.gemini_provider import GeminiProvider
from src.modules.assistant.providers.groq_provider import GroqProvider
from src.modules.assistant.providers.openrouter_provider import OpenRouterProvider


SUPPORTED_PROVIDERS = (
    "gemini",
    "groq",
    "cloudflare",
    "openrouter",
)


def invalidate_provider_cache(name=None):
    """Backward-compatible no-op; request credentials are never cached."""
    return None


def create_provider(
    provider_name="gemini",
    *,
    credentials=None,
    api_key=None,
):
    """Create a request-scoped provider.

    `api_key` remains supported for old Gemini callers/tests.
    """
    provider_name = str(provider_name or "gemini").strip().lower()
    credentials = dict(credentials or {})

    if provider_name == "gemini":
        return GeminiProvider(
            api_key=credentials.get("gemini_api_key") or api_key,
        )
    if provider_name == "groq":
        return GroqProvider(
            api_key=credentials.get("groq_api_key"),
        )
    if provider_name == "cloudflare":
        return CloudflareProvider(
            api_key=credentials.get("cloudflare_api_token"),
            account_id=credentials.get("cloudflare_account_id"),
        )
    if provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=credentials.get("openrouter_api_key"),
        )

    raise ValueError(f"Unsupported AI provider: {provider_name}")
