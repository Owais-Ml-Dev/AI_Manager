"""Cloudflare Workers AI provider."""

import os

from src.modules.assistant.providers.base_provider import ProviderNotConfiguredError
from src.modules.assistant.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


class CloudflareProvider(OpenAICompatibleProvider):
    def __init__(self, api_key=None, account_id=None):
        account_id = str(account_id or "").strip()
        base_url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/ai/v1"
            if account_id
            else ""
        )
        super().__init__(
            api_key=api_key,
            account_id=account_id,
            model=os.getenv(
                "CLOUDFLARE_MODEL",
                "@cf/openai/gpt-oss-20b",
            ).strip(),
            base_url=base_url,
            provider_name="cloudflare",
            display_name="Cloudflare Workers AI",
            timeout=int(os.getenv("CLOUDFLARE_TIMEOUT_SECONDS", "45")),
        )

    def _require_configuration(self):
        if not self.account_id:
            raise ProviderNotConfiguredError(
                "Cloudflare Account ID is not configured."
            )
        super()._require_configuration()
