"""OpenRouter free-model router provider."""

import os

from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, api_key=None):
        super().__init__(
            api_key=api_key,
            model=os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
            base_url=os.getenv(
                "OPENROUTER_BASE_URL",
                "https://openrouter.ai/api/v1",
            ).strip(),
            provider_name="openrouter",
            display_name="OpenRouter",
            timeout=int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")),
            extra_headers={"X-Title": "AI Task Manager"},
        )
