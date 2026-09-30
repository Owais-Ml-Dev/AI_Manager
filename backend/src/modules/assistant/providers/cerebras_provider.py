"""Cerebras Inference provider."""

import os

from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class CerebrasProvider(
    OpenAICompatibleProvider
):
    def __init__(
        self,
        api_key=None,
    ):
        super().__init__(
            api_key=api_key,

            model=os.getenv(
                "CEREBRAS_MODEL",
                "gpt-oss-120b",
            ).strip(),

            base_url=os.getenv(
                "CEREBRAS_BASE_URL",
                "https://api.cerebras.ai/v1",
            ).strip(),

            provider_name="cerebras",

            display_name="Cerebras",

            timeout=int(
                os.getenv(
                    "CEREBRAS_TIMEOUT_SECONDS",
                    "45",
                )
            ),
        )
