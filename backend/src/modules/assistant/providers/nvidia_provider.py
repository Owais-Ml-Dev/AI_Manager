"""NVIDIA hosted NIM provider."""

import os

from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class NvidiaProvider(
    OpenAICompatibleProvider
):
    def __init__(
        self,
        api_key=None,
    ):
        super().__init__(
            api_key=api_key,

            model=os.getenv(
                "NVIDIA_MODEL",
                "openai/gpt-oss-20b",
            ).strip(),

            base_url=os.getenv(
                "NVIDIA_BASE_URL",
                "https://integrate.api.nvidia.com/v1",
            ).strip(),

            provider_name="nvidia",

            display_name="NVIDIA NIM",

            timeout=int(
                os.getenv(
                    "NVIDIA_TIMEOUT_SECONDS",
                    "60",
                )
            ),
        )
