"""Google Gemini API provider.

The Gemini API key is supplied by the client for each request and is never
persisted by this provider.
"""

import json
import os
import random
import time

import requests
from requests.adapters import HTTPAdapter

from src.modules.assistant.providers.base_provider import (
    BaseProvider,
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.modules.assistant.providers.reasoning_policy import gemini_thinking_level


_GEMINI_HTTP_SESSION = requests.Session()
_GEMINI_HTTP_SESSION.mount(
    "https://",
    HTTPAdapter(
        pool_connections=4,
        pool_maxsize=4,
        max_retries=0,
    ),
)


class GeminiProvider(BaseProvider):
    provider_name = "gemini"
    provider_type = "api"
    _RETRYABLE_STATUS_CODES = (500, 502, 503, 504)

    def __init__(self, api_key=None):
        self.api_key = str(api_key or "").strip()
        self.credential_source = "request" if self.api_key else None
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        self.base_url = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
        self.timeout = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
        self.retry_backoff_seconds = float(
            os.getenv("GEMINI_RETRY_BACKOFF_SECONDS", "1.5")
        )
        # On Gemini 3.x the model's thinking tokens are counted inside
        # maxOutputTokens, and thinking cannot be switched off. 1024 left
        # too little room for the actual answer.
        self.max_output_tokens = int(
            os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048")
        )
        self.structured_max_output_tokens = int(
            os.getenv("GEMINI_STRUCTURED_MAX_OUTPUT_TOKENS", "4096")
        )

        # Lowest thinking level the model accepts. Gemini 3.8/3.7 Flash:
        # low | medium | high (default is MEDIUM). "minimal" is rejected
        # there, and thinkingBudget:0 is not honoured on Gemini 3 -- which
        # is why every request, even "hi", was running at medium thinking.
        self.fast_thinking_level = (
            os.getenv("GEMINI_FAST_THINKING_LEVEL", "low").strip().lower() or "low"
        )

        # Hard wall-clock cap across all retries. Must stay below the
        # Flutter client's receive timeout, otherwise the app gives up while
        # the server keeps retrying.
        self.total_deadline_seconds = float(
            os.getenv("GEMINI_TOTAL_DEADLINE_SECONDS", "40")
        )

        # Backup models, tried in order when the main model is overloaded
        # (503), rate-limited (429) or times out. Each Gemini model has its
        # own capacity and its own free-tier quota. Set to empty to disable.
        self.fallback_models = [
            name.strip()
            for name in os.getenv(
                "GEMINI_FALLBACK_MODELS",
                "gemini-3.5-flash,gemini-3.1-flash-lite",
            ).split(",")
            if name.strip()
        ]
        self.model_used = self.model

    def _require_configuration(self):
        if not self.api_key:
            raise ProviderNotConfiguredError("Gemini API key is not configured.")
        if not self.model:
            raise ProviderNotConfiguredError("GEMINI_MODEL is not configured.")

    # Statuses that mean "this model is busy or out of quota right now".
    # Another model has separate capacity, so it is worth trying.
    _FALLBACK_STATUS_CODES = (429, 500, 502, 503, 504)

    def _post_with_retry(self, payload, model, deadline):
        url = f"{self.base_url}/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        attempts = self.max_retries + 1
        last_error = None
        last_response = None

        for attempt in range(attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 1.0:
                break

            try:
                response = _GEMINI_HTTP_SESSION.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=min(self.timeout, remaining),
                )
            except requests.RequestException as error:
                last_error = error
                last_response = None
                if attempt < attempts - 1 and self._sleep_within(deadline, attempt):
                    continue
                if isinstance(error, requests.Timeout):
                    raise ProviderConnectionError(
                        "Gemini took too long to answer. Please try again."
                    ) from error
                raise ProviderConnectionError(
                    "Could not connect to the Gemini API."
                ) from error

            if (
                response.status_code in self._RETRYABLE_STATUS_CODES
                and attempt < attempts - 1
            ):
                last_response = response
                if self._sleep_within(deadline, attempt):
                    continue
                break

            return response

        if last_response is not None:
            return last_response
        if last_error:
            raise ProviderConnectionError(
                "Could not connect to the Gemini API."
            ) from last_error
        raise ProviderConnectionError("Gemini did not respond in time. Please try again.")

    def _sleep_within(self, deadline, attempt_index):
        """Back off, but only if there is time left for another attempt."""
        delay = self._backoff_delay(attempt_index)
        if deadline - time.monotonic() - delay <= 3.0:
            return False
        time.sleep(delay)
        return True

    def _backoff_delay(self, attempt_index):
        exponent = min(attempt_index, 3)
        ceiling = min(self.retry_backoff_seconds * (2 ** exponent), 8.0)
        return random.uniform(min(0.25, ceiling), ceiling)

    def _uses_thinking_levels(self, model):
        """Gemini 3.x takes thinkingLevel; Gemini 2.x takes thinkingBudget."""
        style = os.getenv("GEMINI_THINKING_STYLE", "auto").strip().lower()
        if style in ("level", "budget"):
            return style == "level"
        return str(model).lower().startswith("gemini-3")

    def _thinking_config(self, level, model=None):
        level = str(level or "").strip().lower()
        wants_fast = level in ("", "off", "none", "disabled", "minimal", "0", "low")

        if self._uses_thinking_levels(model or self.model):
            return {
                "thinkingLevel": self.fast_thinking_level if wants_fast else level
            }

        # Gemini 2.x: thinking can be switched fully off.
        return {"thinkingBudget": 0 if wants_fast else -1}

    def _models_to_try(self):
        models = [self.model]
        for name in self.fallback_models:
            if name and name not in models:
                models.append(name)
        return models

    def _post(self, payload, thinking_level="low"):
        """Send the request, moving to a backup model if Gemini is overloaded.

        "Gemini is temporarily overloaded" (HTTP 503) is Google running out
        of capacity for ONE model at that moment. It is not something our
        code can fix -- but other models have their own capacity, so the
        request is tried on the next model in GEMINI_FALLBACK_MODELS.

        Also: if a model rejects our thinking setting (HTTP 400), resend
        once without it. Different Gemini versions accept different values.

        One shared deadline covers every attempt on every model.
        """

        deadline = time.monotonic() + self.total_deadline_seconds
        models = self._models_to_try()
        last_response = None
        last_error = None

        for index, model in enumerate(models):
            is_last = index == len(models) - 1
            if deadline - time.monotonic() < 3.0:
                break

            model_payload = dict(payload)
            generation = dict(payload.get("generationConfig") or {})
            generation["thinkingConfig"] = self._thinking_config(thinking_level, model)
            model_payload["generationConfig"] = generation

            try:
                response = self._post_with_retry(model_payload, model, deadline)

                if (
                    response.status_code == 400
                    and "think" in (response.text or "").lower()
                ):
                    print(
                        f"[assistant] {model} rejected thinkingConfig "
                        f"{generation['thinkingConfig']}; retrying without it.",
                        flush=True,
                    )
                    generation.pop("thinkingConfig", None)
                    model_payload["generationConfig"] = generation
                    response = self._post_with_retry(model_payload, model, deadline)

            except ProviderConnectionError as error:
                last_error = error
                if not is_last:
                    print(f"[assistant] {model} failed ({error}); trying next model.", flush=True)
                continue

            if response.status_code in self._FALLBACK_STATUS_CODES and not is_last:
                print(
                    f"[assistant] {model} returned HTTP {response.status_code}; "
                    "trying next model.",
                    flush=True,
                )
                last_response = response
                continue

            self.model_used = model
            return response

        if last_response is not None:
            return last_response
        if last_error is not None:
            raise last_error
        raise ProviderConnectionError("Gemini did not respond in time. Please try again.")

    def _raise_for_response_status(self, response):
        if response.status_code == 429:
            raise ProviderRateLimitError(
                "Gemini rate limit reached. Wait a moment and try again."
            )
        if response.status_code in (502, 503, 504):
            raise ProviderConnectionError(
                "Gemini is temporarily overloaded. Please try again in a moment."
            )
        if response.status_code == 500:
            raise ProviderConnectionError(
                "Gemini returned a server error. Please try again in a moment."
            )
        if not response.ok:
            raise ProviderConnectionError(
                f"Gemini returned an error (HTTP {response.status_code})."
            )

    def _response_text(self, response):
        self._raise_for_response_status(response)
        try:
            data = response.json()
            candidate = data["candidates"][0]
            parts = (candidate.get("content") or {}).get("parts") or []
            # Parts marked "thought" are the model's reasoning, not its answer.
            text = "".join(
                part.get("text", "")
                for part in parts
                if isinstance(part, dict) and not part.get("thought")
            ).strip()
        except (
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ) as error:
            raise ProviderResponseError(
                "Gemini returned an unexpected response."
            ) from error

        if not text:
            finish = candidate.get("finishReason")
            if finish == "MAX_TOKENS":
                raise ProviderResponseError(
                    "Gemini ran out of output space before answering. "
                    "Raise GEMINI_MAX_OUTPUT_TOKENS in .env."
                )
            raise ProviderResponseError(
                "Gemini returned an empty response"
                + (f" ({finish})." if finish else ".")
            )
        return text

    def _base_payload(self, message, system_prompt):
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": message}],
                }
            ]
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        return payload

    def chat(self, message, system_prompt):
        """Normal conversational Gemini call."""
        self._require_configuration()
        payload = self._base_payload(message, system_prompt)
        payload["generationConfig"] = {
            "maxOutputTokens": self.max_output_tokens,
        }
        # `message` here is exactly what the user typed, so the heuristic is
        # judging the right text.
        return self._response_text(
            self._post(payload, thinking_level=gemini_thinking_level(message))
        )

    def structured_json(self, message, system_prompt, response_schema):
        """Generate JSON constrained by Gemini's response schema.

        This is used by the task parser so Gemini cannot return prose around the
        task command.  The returned value is a Python dictionary.
        """
        self._require_configuration()
        payload = self._base_payload(message, system_prompt)
        payload["generationConfig"] = {
            "maxOutputTokens": self.structured_max_output_tokens,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        }

        # Filling a JSON schema from one sentence is transcription, not
        # reasoning: always the lowest thinking level.
        text = self._response_text(self._post(payload, thinking_level="low"))
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as error:
            raise ProviderResponseError(
                "Gemini did not return valid structured JSON."
            ) from error

        if not isinstance(value, dict):
            raise ProviderResponseError(
                "Gemini structured output was not a JSON object."
            )
        return value

    def health(self):
        """Validate Gemini API connectivity without generating content."""
        if not self.api_key:
            return {
                **self.metadata(),
                "configured": False,
                "available": False,
                "message": "Gemini API key is not configured.",
            }

        try:
            response = _GEMINI_HTTP_SESSION.get(
                f"{self.base_url}/models",
                headers={"x-goog-api-key": self.api_key},
                params={"pageSize": 1},
                timeout=10,
            )
            return {
                **self.metadata(),
                "configured": True,
                "available": response.ok,
                "message": (
                    "Gemini API is reachable."
                    if response.ok
                    else (
                        "Gemini API credentials/configuration failed "
                        f"(HTTP {response.status_code})."
                    )
                ),
            }
        except requests.RequestException:
            return {
                **self.metadata(),
                "configured": True,
                "available": False,
                "message": "Gemini API is not reachable.",
            }
