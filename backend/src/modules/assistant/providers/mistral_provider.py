"""Mistral API provider."""

import os

from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class MistralProvider(
    OpenAICompatibleProvider
):
    def __init__(
        self,
        api_key=None,
    ):
        super().__init__(
            api_key=api_key,

            model=os.getenv(
                "MISTRAL_MODEL",
                "mistral-small-latest",
            ).strip(),

            base_url=os.getenv(
                "MISTRAL_BASE_URL",
                "https://api.mistral.ai/v1",
            ).strip(),

            provider_name="mistral",

            display_name="Mistral",

            timeout=int(
                os.getenv(
                    "MISTRAL_TIMEOUT_SECONDS",
                    "45",
                )
            ),
        )
