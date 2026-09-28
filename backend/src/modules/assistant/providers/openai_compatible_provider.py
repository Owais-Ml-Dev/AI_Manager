"""Shared OpenAI-compatible cloud provider adapter."""

import json
import re

import requests

from src.modules.assistant.providers.base_provider import (
    BaseProvider,
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)


_JSON_FENCE = re.compile(r"^```(?:json)?\\s*|\\s*```$", re.IGNORECASE)


class OpenAICompatibleProvider(BaseProvider):
    provider_type = "api"
    display_name = "AI provider"

    def __init__(
        self,
        *,
        api_key=None,
        model,
        base_url,
        provider_name,
        display_name,
        account_id=None,
        timeout=45,
        extra_headers=None,
    ):
        self.api_key = str(api_key or "").strip()
        self.account_id = str(account_id or "").strip()
        self.model = str(model or "").strip()
        self.model_used = self.model
        self.base_url = str(base_url or "").rstrip("/")
        self.provider_name = provider_name
        self.display_name = display_name
        self.timeout = int(timeout)
        self.extra_headers = dict(extra_headers or {})

    def _require_configuration(self):
        if not self.api_key:
            raise ProviderNotConfiguredError(
                f"{self.display_name} API key is not configured."
            )
        if not self.model:
            raise ProviderNotConfiguredError(
                f"{self.display_name} model is not configured."
            )
        if not self.base_url:
            raise ProviderNotConfiguredError(
                f"{self.display_name} API URL is not configured."
            )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def _messages(self, message, system_prompt):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return messages

    def _raise_for_status(self, response):
        status = int(response.status_code)
        if status in (401, 403):
            raise ProviderNotConfiguredError(
                f"{self.display_name} rejected the configured credentials "
                f"(HTTP {status})."
            )
        if status in (402, 429):
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after = float(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after = None
            error = ProviderRateLimitError(
                f"{self.display_name} quota or rate limit was reached."
            )
            error.retry_after_seconds = retry_after
            raise error
        if status in (500, 502, 503, 504):
            raise ProviderConnectionError(
                f"{self.display_name} is temporarily unavailable "
                f"(HTTP {status})."
            )
        if not response.ok:
            raise ProviderResponseError(
                f"{self.display_name} rejected the request "
                f"(HTTP {status})."
            )

    def _post(self, payload):
        self._require_configuration()
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise ProviderConnectionError(
                f"{self.display_name} took too long to answer."
            ) from error
        except requests.RequestException as error:
            raise ProviderConnectionError(
                f"Could not connect to {self.display_name}."
            ) from error
        self._raise_for_status(response)
        return response

    def _response_text(self, response):
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderResponseError(
                f"{self.display_name} returned an unexpected response."
            ) from error
        if isinstance(text, list):
            text = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in text
            )
        text = str(text or "").strip()
        if not text:
            raise ProviderResponseError(
                f"{self.display_name} returned an empty response."
            )
        return text

    def chat(self, message, system_prompt):
        payload = {
            "model": self.model,
            "messages": self._messages(message, system_prompt),
            "max_tokens": 2048,
            "stream": False,
        }
        return self._response_text(self._post(payload))

    def structured_json(self, message, system_prompt, response_schema):
        schema_text = json.dumps(response_schema, ensure_ascii=False)
        strict_prompt = (
            (system_prompt or "")
            + "\n\nReturn ONLY one valid JSON object. Do not use markdown. "
            + "It must match this JSON Schema exactly:\n"
            + schema_text
        )
        base = {
            "model": self.model,
            "messages": self._messages(message, strict_prompt),
            "max_tokens": 4096,
            "stream": False,
        }

        response = None
        # Prefer schema-constrained output. If a specific routed model does not
        # support it, degrade to JSON Object mode, then prompt-only JSON.
        response_formats = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "task_intent",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            {"type": "json_object"},
            None,
        ]

        for response_format in response_formats:
            payload = dict(base)
            if response_format is not None:
                payload["response_format"] = response_format
            try:
                response = self._post(payload)
                break
            except ProviderResponseError as error:
                # 400/422 can mean this provider/model does not support the
                # requested response_format. Try the next compatibility mode.
                if response_format is None:
                    raise
                continue

        if response is None:
            raise ProviderResponseError(
                f"{self.display_name} could not produce structured JSON."
            )

        text = self._response_text(response)
        text = _JSON_FENCE.sub("", text).strip()
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as error:
            raise ProviderResponseError(
                f"{self.display_name} did not return valid JSON."
            ) from error
        if not isinstance(value, dict):
            raise ProviderResponseError(
                f"{self.display_name} structured output was not a JSON object."
            )
        return value

    def health(self):
        if not self.api_key:
            return {
                **self.metadata(),
                "configured": False,
                "available": False,
                "message": f"{self.display_name} API key is not configured.",
            }
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply only OK"}],
                "max_tokens": 8,
                "stream": False,
            }
            self._post(payload)
        except ProviderNotConfiguredError as error:
            return {
                **self.metadata(),
                "configured": True,
                "available": False,
                "message": str(error),
            }
        except (ProviderRateLimitError, ProviderConnectionError, ProviderResponseError) as error:
            return {
                **self.metadata(),
                "configured": True,
                "available": False,
                "message": str(error),
            }
        return {
            **self.metadata(),
            "configured": True,
            "available": True,
            "message": f"{self.display_name} is reachable.",
        }
