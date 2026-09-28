"""Groq Cloud provider."""

import os

from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, api_key=None):
        super().__init__(
            api_key=api_key,
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
            base_url=os.getenv(
                "GROQ_BASE_URL",
                "https://api.groq.com/openai/v1",
            ).strip(),
            provider_name="groq",
            display_name="Groq",
            timeout=int(os.getenv("GROQ_TIMEOUT_SECONDS", "45")),
        )
