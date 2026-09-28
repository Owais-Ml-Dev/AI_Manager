from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('.').resolve()
B = ROOT / 'backend'
F = ROOT / 'frontend'
if not B.exists(): B = ROOT
if not F.exists(): F = ROOT

# Safety backup of every existing file this patch modifies.
stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_root = ROOT / f'.multi_provider_backup_{stamp}'
backup_targets = [
    B / 'src/modules/assistant/providers/provider_factory.py',
    B / 'src/modules/assistant/service.py',
    B / 'src/modules/assistant/task_parser.py',
    B / 'src/modules/assistant/drafts/service.py',
    B / 'src/modules/assistant/controller.py',
    F / 'lib/core/security/gemini_api_key_store.dart',
    F / 'lib/features/settings/domain/assistant_settings_data.dart',
    F / 'lib/features/settings/data/assistant_settings_repository.dart',
    F / 'lib/features/settings/presentation/settings_screen.dart',
    F / 'lib/features/assistant/data/assistant_repository.dart',
]
for source in backup_targets:
    if not source.exists():
        continue
    try:
        relative = source.relative_to(ROOT)
    except ValueError:
        relative = Path(source.name)
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
print('BACKUP', backup_root)

def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.lstrip('\n'), encoding='utf-8')
    print('WROTE', path)

# ---------------- Backend new provider files ----------------
providers = B / 'src/modules/assistant/providers'
write(providers / 'openai_compatible_provider.py', r'''
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
''')

write(providers / 'groq_provider.py', r'''
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
''')

write(providers / 'cloudflare_provider.py', r'''
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
''')

write(providers / 'openrouter_provider.py', r'''
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
''')

write(providers / 'provider_factory.py', r'''
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
''')

write(providers / 'provider_router.py', r'''
"""Automatic multi-provider fallback router.

Priority:
    Gemini -> Groq -> Cloudflare Workers AI -> OpenRouter Free

A provider that is temporarily rate-limited is cooled down for a short period
so the next request moves immediately to the next configured provider.
"""

import os
import time

from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.modules.assistant.providers.provider_factory import create_provider


DEFAULT_PROVIDER_PRIORITY = (
    "gemini",
    "groq",
    "cloudflare",
    "openrouter",
)

_cooldowns = {}


def _priority():
    configured = [
        value.strip().lower()
        for value in os.getenv(
            "AI_PROVIDER_PRIORITY",
            ",".join(DEFAULT_PROVIDER_PRIORITY),
        ).split(",")
        if value.strip()
    ]
    return tuple(configured or DEFAULT_PROVIDER_PRIORITY)


def _merge_credentials(credentials=None, api_key=None):
    value = dict(credentials or {})
    if api_key and not value.get("gemini_api_key"):
        value["gemini_api_key"] = api_key
    return value


def _has_credentials(name, credentials):
    if name == "gemini":
        return bool(credentials.get("gemini_api_key"))
    if name == "groq":
        return bool(credentials.get("groq_api_key"))
    if name == "cloudflare":
        return bool(
            credentials.get("cloudflare_api_token")
            and credentials.get("cloudflare_account_id")
        )
    if name == "openrouter":
        return bool(credentials.get("openrouter_api_key"))
    return False


def _cooldown_active(name):
    until = _cooldowns.get(name, 0)
    if until <= time.monotonic():
        _cooldowns.pop(name, None)
        return False
    return True


def _mark_failure(name, error):
    if isinstance(error, ProviderRateLimitError):
        delay = getattr(error, "retry_after_seconds", None)
        if not delay:
            delay = float(os.getenv("AI_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS", "120"))
    elif isinstance(error, ProviderNotConfiguredError):
        delay = float(os.getenv("AI_PROVIDER_AUTH_COOLDOWN_SECONDS", "300"))
    else:
        delay = float(os.getenv("AI_PROVIDER_ERROR_COOLDOWN_SECONDS", "20"))
    _cooldowns[name] = time.monotonic() + max(1.0, float(delay))


def _candidate_names(credentials):
    priority = _priority()
    configured = [name for name in priority if _has_credentials(name, credentials)]
    return configured


def _run(method_name, *, credentials=None, api_key=None, **kwargs):
    credentials = _merge_credentials(credentials, api_key)
    candidates = _candidate_names(credentials)
    if not candidates:
        raise ProviderNotConfiguredError(
            "Add at least one AI provider API key in Settings."
        )

    attempted = []
    errors = []
    first = candidates[0]

    # Try providers not in cooldown first. If every configured provider is in
    # cooldown, do a normal pass anyway so recovery does not require a restart.
    passes = [False, True]
    for allow_cooldown in passes:
        for name in candidates:
            if name in attempted:
                continue
            if not allow_cooldown and _cooldown_active(name):
                continue

            attempted.append(name)
            provider = create_provider(name, credentials=credentials)
            try:
                result = getattr(provider, method_name)(**kwargs)
                return {
                    "provider": name,
                    "type": getattr(provider, "provider_type", "api"),
                    "model": getattr(provider, "model_used", provider.model),
                    "result": result,
                    "fallback_used": name != first,
                    "attempted_providers": list(attempted),
                }
            except (
                ProviderNotConfiguredError,
                ProviderRateLimitError,
                ProviderConnectionError,
                ProviderResponseError,
            ) as error:
                errors.append((name, error))
                _mark_failure(name, error)
                print(
                    f"[assistant] {name} unavailable ({error}); trying fallback.",
                    flush=True,
                )

    if errors:
        raise errors[-1][1]
    raise ProviderConnectionError("No AI provider was available.")


def chat_with_fallback(message, system_prompt, *, credentials=None, api_key=None):
    return _run(
        "chat",
        credentials=credentials,
        api_key=api_key,
        message=message,
        system_prompt=system_prompt,
    )


def structured_json_with_fallback(
    message,
    system_prompt,
    response_schema,
    *,
    credentials=None,
    api_key=None,
):
    return _run(
        "structured_json",
        credentials=credentials,
        api_key=api_key,
        message=message,
        system_prompt=system_prompt,
        response_schema=response_schema,
    )


def provider_health(provider_name, *, credentials=None, api_key=None):
    credentials = _merge_credentials(credentials, api_key)
    provider = create_provider(
        provider_name,
        credentials=credentials,
        api_key=api_key,
    )
    return provider.health()
''')

# service.py
write(B / 'src/modules/assistant/service.py', r'''
"""Multi-provider assistant service.

Cloud models interpret chat/task language. Draft validation, confirmation,
execution and persistence remain deterministic backend concerns.
"""

from src.modules.assistant.drafts.service import (
    execute_task_draft,
    preview_task_draft,
    select_draft_target,
)
from src.modules.assistant.prompts.chat_prompt import CHAT_SYSTEM_PROMPT
from src.modules.assistant.providers.provider_router import (
    chat_with_fallback,
    provider_health,
)


def get_assistant_status(api_key=None, provider_name="gemini", credentials=None):
    return provider_health(
        provider_name,
        credentials=credentials,
        api_key=api_key,
    )


def send_chat(message, api_key=None, credentials=None):
    routed = chat_with_fallback(
        message=message,
        system_prompt=CHAT_SYSTEM_PROMPT,
        credentials=credentials,
        api_key=api_key,
    )
    return {
        "provider": routed["provider"],
        "type": routed["type"],
        "model": routed["model"],
        "reply": routed["result"],
        "fallback_used": routed["fallback_used"],
        "attempted_providers": routed["attempted_providers"],
    }


def preview_task_command(
    message,
    timezone_name="UTC",
    api_key=None,
    draft_id=None,
    credentials=None,
):
    return preview_task_draft(
        message=message,
        timezone_name=timezone_name,
        api_key=api_key,
        credentials=credentials,
        draft_id=draft_id,
    )


def choose_task_target(draft_id, task_id):
    return select_draft_target(draft_id=draft_id, task_id=task_id)


def run_task_command(
    draft_id,
    confirmed=False,
    duplicate_decision=None,
    candidate_id=None,
):
    return execute_task_draft(
        draft_id=draft_id,
        confirmed=confirmed,
        duplicate_decision=duplicate_decision,
        candidate_id=candidate_id,
    )
''')

# Patch task_parser import + signature/body
p = B / 'src/modules/assistant/task_parser.py'
text = p.read_text(encoding='utf-8')
text = text.replace(
    'from src.modules.assistant.providers.provider_factory import create_provider\n',
    'from src.modules.assistant.providers.provider_router import structured_json_with_fallback\n',
    1,
)
text = text.replace(
'''def parse_task_message(\n    message,\n    timezone_name="UTC",\n    api_key=None,\n    current_draft=None,\n    pending_question=None,\n):''',
'''def parse_task_message(\n    message,\n    timezone_name="UTC",\n    api_key=None,\n    credentials=None,\n    current_draft=None,\n    pending_question=None,\n):''',
1,
)
old = '''    provider = create_provider(api_key=api_key)\n    started = time.monotonic()\n    parsed = provider.structured_json(\n        message=user_prompt,\n        system_prompt=TASK_COMMAND_SYSTEM_PROMPT,\n        response_schema=TASK_INTENT_RESPONSE_SCHEMA,\n    )\n\n    # Visible in the Flask terminal: what Gemini actually returned and how\n    # long it took. If the assistant ever misunderstands something, this\n    # line shows whether Gemini or the backend is responsible.\n    print(\n        "[assistant] Gemini parse %.1fs -> %s"\n        % (time.monotonic() - started, json.dumps(parsed, ensure_ascii=False)[:500]),\n        flush=True,\n    )\n\n    return {\n        "provider": "gemini",\n        "type": "api",\n        "model": getattr(provider, "model_used", provider.model),\n        "timezone": timezone_name,\n        "local_now": now,\n        "intent": _sanitize_intent(parsed),\n    }'''
new = '''    started = time.monotonic()\n    routed = structured_json_with_fallback(\n        message=user_prompt,\n        system_prompt=TASK_COMMAND_SYSTEM_PROMPT,\n        response_schema=TASK_INTENT_RESPONSE_SCHEMA,\n        credentials=credentials,\n        api_key=api_key,\n    )\n    parsed = routed["result"]\n\n    print(\n        "[assistant] %s parse %.1fs -> %s"\n        % (\n            routed["provider"],\n            time.monotonic() - started,\n            json.dumps(parsed, ensure_ascii=False)[:500],\n        ),\n        flush=True,\n    )\n\n    return {\n        "provider": routed["provider"],\n        "type": routed["type"],\n        "model": routed["model"],\n        "timezone": timezone_name,\n        "local_now": now,\n        "intent": _sanitize_intent(parsed),\n        "fallback_used": routed["fallback_used"],\n        "attempted_providers": routed["attempted_providers"],\n    }'''
if old not in text:
    raise RuntimeError('task_parser provider block not found')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
print('PATCHED', p)

# Patch drafts service signature and call / catch
p = B / 'src/modules/assistant/drafts/service.py'
text = p.read_text(encoding='utf-8')
text = text.replace(
'''from src.modules.assistant.providers.base_provider import (\n    ProviderConnectionError,\n    ProviderResponseError,\n)''',
'''from src.modules.assistant.providers.base_provider import (\n    ProviderConnectionError,\n    ProviderNotConfiguredError,\n    ProviderResponseError,\n)''',
1,
)
text = text.replace(
'''def preview_task_draft(\n    message,\n    timezone_name="UTC",\n    api_key=None,\n    draft_id=None,\n):''',
'''def preview_task_draft(\n    message,\n    timezone_name="UTC",\n    api_key=None,\n    credentials=None,\n    draft_id=None,\n):''',
1,
)
old_call = '''            parsed = parse_task_message(\n                message=message,\n                timezone_name=timezone_name,\n                api_key=api_key,\n                current_draft=current_intent,\n                pending_question=(existing or {}).get("question") if answering else None,\n            )'''
new_call = '''            parse_kwargs = {\n                "message": message,\n                "timezone_name": timezone_name,\n                "api_key": api_key,\n                "current_draft": current_intent,\n                "pending_question": (existing or {}).get("question") if answering else None,\n            }\n            if credentials is not None:\n                parse_kwargs["credentials"] = credentials\n            parsed = parse_task_message(**parse_kwargs)'''
if old_call not in text:
    raise RuntimeError('draft parse call not found')
text = text.replace(old_call, new_call, 1)
text = text.replace(
'except (ProviderConnectionError, ProviderResponseError) as error:',
'except (ProviderNotConfiguredError, ProviderConnectionError, ProviderResponseError) as error:',
1,
)
text = text.replace(
'print(f"[assistant] Gemini unavailable ({error}); using local parse.", flush=True)',
'print(f"[assistant] cloud providers unavailable ({error}); using local parse.", flush=True)',
1,
)
p.write_text(text, encoding='utf-8')
print('PATCHED', p)

# Patch controller helpers + specific call sites while preserving old Gemini-only tests.
p = B / 'src/modules/assistant/controller.py'
text = p.read_text(encoding='utf-8')
anchor = '''def _request_gemini_api_key():\n    """Read the per-request Gemini key. Never log or persist it."""\n    return request.headers.get("X-Gemini-Api-Key", "").strip()\n'''
helper = anchor + r'''


def _request_provider_credentials():
    """Read request-scoped provider credentials without logging them."""
    return {
        "gemini_api_key": _request_gemini_api_key(),
        "groq_api_key": request.headers.get("X-Groq-Api-Key", "").strip(),
        "cloudflare_api_token": request.headers.get(
            "X-Cloudflare-Api-Token", ""
        ).strip(),
        "cloudflare_account_id": request.headers.get(
            "X-Cloudflare-Account-Id", ""
        ).strip(),
        "openrouter_api_key": request.headers.get(
            "X-OpenRouter-Api-Key", ""
        ).strip(),
    }


def _has_non_gemini_credentials(credentials):
    return any(
        credentials.get(name)
        for name in (
            "groq_api_key",
            "cloudflare_api_token",
            "openrouter_api_key",
        )
    )
'''
if anchor not in text:
    raise RuntimeError('controller gemini helper not found')
text = text.replace(anchor, helper, 1)

old = '''def get_assistant_health_controller():\n    return jsonify({\n        "success": True,\n        "data": get_assistant_status(api_key=_request_gemini_api_key()),\n    }), 200'''
new = '''def get_assistant_health_controller():\n    provider_name = request.args.get("provider", "gemini").strip().lower() or "gemini"\n    credentials = _request_provider_credentials()\n\n    if provider_name == "gemini" and not _has_non_gemini_credentials(credentials):\n        data = get_assistant_status(api_key=_request_gemini_api_key())\n    else:\n        data = get_assistant_status(\n            api_key=_request_gemini_api_key(),\n            provider_name=provider_name,\n            credentials=credentials,\n        )\n\n    return jsonify({"success": True, "data": data}), 200'''
if old not in text:
    raise RuntimeError('health controller block not found')
text = text.replace(old, new, 1)

old = '''        result = send_chat(\n            message=message.strip(),\n            api_key=_request_gemini_api_key(),\n        )'''
new = '''        credentials = _request_provider_credentials()\n        if _has_non_gemini_credentials(credentials):\n            result = send_chat(\n                message=message.strip(),\n                api_key=_request_gemini_api_key(),\n                credentials=credentials,\n            )\n        else:\n            result = send_chat(\n                message=message.strip(),\n                api_key=_request_gemini_api_key(),\n            )'''
if old not in text:
    raise RuntimeError('chat controller call not found')
text = text.replace(old, new, 1)

old = '''        result = preview_task_command(\n            message=message.strip(),\n            timezone_name=timezone_name.strip() or "UTC",\n            api_key=_request_gemini_api_key(),\n            draft_id=draft_id.strip() if isinstance(draft_id, str) else None,\n        )'''
new = '''        credentials = _request_provider_credentials()\n        kwargs = {\n            "message": message.strip(),\n            "timezone_name": timezone_name.strip() or "UTC",\n            "api_key": _request_gemini_api_key(),\n            "draft_id": draft_id.strip() if isinstance(draft_id, str) else None,\n        }\n        if _has_non_gemini_credentials(credentials):\n            kwargs["credentials"] = credentials\n        result = preview_task_command(**kwargs)'''
if old not in text:
    raise RuntimeError('preview controller call not found')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
print('PATCHED', p)

# ---------------- Frontend ----------------
security = F / 'lib/core/security/gemini_api_key_store.dart'
write(security, r'''
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class GeminiApiKeyStore {
  static const _geminiKey = 'gemini_api_key';
  static const _groqKey = 'groq_api_key';
  static const _cloudflareTokenKey = 'cloudflare_api_token';
  static const _cloudflareAccountIdKey = 'cloudflare_account_id';
  static const _openRouterKey = 'openrouter_api_key';

  final FlutterSecureStorage _storage;

  const GeminiApiKeyStore({this._storage = const FlutterSecureStorage()});

  String _storageKey(String provider) {
    switch (provider) {
      case 'gemini':
        return _geminiKey;
      case 'groq':
        return _groqKey;
      case 'cloudflare':
        return _cloudflareTokenKey;
      case 'openrouter':
        return _openRouterKey;
      default:
        throw ArgumentError('Unsupported AI provider: $provider');
    }
  }

  Future<String?> _readKey(String key) async {
    final value = await _storage.read(key: key);
    final normalized = value?.trim();
    return normalized == null || normalized.isEmpty ? null : normalized;
  }

  Future<String?> readProviderApiKey(String provider) {
    return _readKey(_storageKey(provider));
  }

  Future<void> saveProviderApiKey(String provider, String apiKey) async {
    final normalized = apiKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError('API key is required.');
    }
    await _storage.write(key: _storageKey(provider), value: normalized);
  }

  Future<void> deleteProviderApiKey(String provider) {
    return _storage.delete(key: _storageKey(provider));
  }

  Future<String?> readCloudflareAccountId() {
    return _readKey(_cloudflareAccountIdKey);
  }

  Future<void> saveCloudflareAccountId(String accountId) async {
    final normalized = accountId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError('Cloudflare Account ID is required.');
    }
    await _storage.write(key: _cloudflareAccountIdKey, value: normalized);
  }

  Future<void> deleteCloudflareAccountId() {
    return _storage.delete(key: _cloudflareAccountIdKey);
  }

  // Backward-compatible Gemini helpers used by Live Voice and older tests.
  Future<String?> read() => readProviderApiKey('gemini');
  Future<void> save(String apiKey) => saveProviderApiKey('gemini', apiKey);
  Future<void> delete() => deleteProviderApiKey('gemini');
}
''')

write(F / 'lib/features/settings/domain/assistant_settings_data.dart', r'''
class AssistantProviderSettings {
  final String provider;
  final String label;
  final String model;
  final bool configured;
  final String? keyHint;
  final String? accountId;
  final bool requiresAccountId;

  const AssistantProviderSettings({
    required this.provider,
    required this.label,
    required this.model,
    required this.configured,
    required this.keyHint,
    this.accountId,
    this.requiresAccountId = false,
  });
}

class AssistantSettingsData {
  final List<AssistantProviderSettings> providers;
  final String message;

  const AssistantSettingsData({required this.providers, this.message = ''});

  AssistantProviderSettings? provider(String name) {
    for (final item in providers) {
      if (item.provider == name) return item;
    }
    return null;
  }

  bool get anyProviderConfigured => providers.any((item) => item.configured);

  // Compatibility getters for existing callers.
  String get model => provider('gemini')?.model ?? 'gemini-3.8-flash';
  bool get configured => anyProviderConfigured;
  bool get available => anyProviderConfigured;
  bool get storedKeyConfigured => provider('gemini')?.configured ?? false;
  String? get keyHint => provider('gemini')?.keyHint;
}
''')

write(F / 'lib/features/settings/data/assistant_settings_repository.dart', r'''
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/gemini_api_key_store.dart';
import '../domain/assistant_settings_data.dart';

class AssistantSettingsRepository {
  final ApiClient _apiClient;
  final GeminiApiKeyStore _keyStore;

  AssistantSettingsRepository(this._apiClient, this._keyStore);

  static const _providerModels = <String, String>{
    'gemini': 'gemini-3.8-flash',
    'groq': 'openai/gpt-oss-20b',
    'cloudflare': '@cf/openai/gpt-oss-20b',
    'openrouter': 'openrouter/free',
  };

  static const _providerLabels = <String, String>{
    'gemini': 'Gemini',
    'groq': 'Groq',
    'cloudflare': 'Cloudflare Workers AI',
    'openrouter': 'OpenRouter Free',
  };

  Future<AssistantSettingsData> fetch() async {
    final providers = <AssistantProviderSettings>[];
    final cloudflareAccountId = await _keyStore.readCloudflareAccountId();

    for (final provider in _providerModels.keys) {
      final key = await _keyStore.readProviderApiKey(provider);
      providers.add(
        AssistantProviderSettings(
          provider: provider,
          label: _providerLabels[provider]!,
          model: _providerModels[provider]!,
          configured: key != null &&
              (provider != 'cloudflare' || cloudflareAccountId != null),
          keyHint: key == null ? null : _keyHint(key),
          accountId: provider == 'cloudflare' ? cloudflareAccountId : null,
          requiresAccountId: provider == 'cloudflare',
        ),
      );
    }

    return AssistantSettingsData(
      providers: providers,
      message: providers.any((item) => item.configured)
          ? 'Automatic fallback is enabled. The first available provider is used.'
          : 'Add at least one provider API key to use the AI Assistant.',
    );
  }

  Future<void> testAndSaveProvider(
    String provider,
    String apiKey, {
    String? accountId,
  }) async {
    final normalized = apiKey.trim();
    if (normalized.isEmpty) {
      throw ApiException(message: '${_providerLabels[provider] ?? provider} API key is required.');
    }

    final headers = <String, dynamic>{};
    switch (provider) {
      case 'gemini':
        headers['X-Gemini-Api-Key'] = normalized;
        break;
      case 'groq':
        headers['X-Groq-Api-Key'] = normalized;
        break;
      case 'cloudflare':
        var normalizedAccountId = (accountId ?? '').trim();
        if (normalizedAccountId.isEmpty) {
          normalizedAccountId = (await _keyStore.readCloudflareAccountId()) ?? '';
        }
        if (normalizedAccountId.isEmpty) {
          throw const ApiException(message: 'Cloudflare Account ID is required.');
        }
        headers['X-Cloudflare-Api-Token'] = normalized;
        headers['X-Cloudflare-Account-Id'] = normalizedAccountId;
        accountId = normalizedAccountId;
        break;
      case 'openrouter':
        headers['X-OpenRouter-Api-Key'] = normalized;
        break;
      default:
        throw ApiException(message: 'Unsupported AI provider: $provider');
    }

    final health = _asMap(
      await _apiClient.get(
        '/api/assistant/health',
        queryParameters: {'provider': provider},
        headers: headers,
      ),
    );

    if (health['available'] != true) {
      throw ApiException(
        message: health['message']?.toString() ??
            '${_providerLabels[provider] ?? provider} rejected these credentials.',
      );
    }

    await _keyStore.saveProviderApiKey(provider, normalized);
    if (provider == 'cloudflare') {
      await _keyStore.saveCloudflareAccountId((accountId ?? '').trim());
    }
  }

  Future<void> deleteProvider(String provider) async {
    await _keyStore.deleteProviderApiKey(provider);
    if (provider == 'cloudflare') {
      await _keyStore.deleteCloudflareAccountId();
    }
  }

  // Existing Gemini API remains available for older callers.
  Future<void> saveApiKey(String apiKey) => testAndSaveProvider('gemini', apiKey);
  Future<void> deleteApiKey() => deleteProvider('gemini');

  String _keyHint(String apiKey) {
    if (apiKey.length <= 4) return '****';
    return '****${apiKey.substring(apiKey.length - 4)}';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}
''')

# Rewrite settings screen
write(F / 'lib/features/settings/presentation/settings_screen.dart', r'''
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/theme_mode_provider.dart';
import '../application/assistant_settings_providers.dart';
import '../domain/assistant_settings_data.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late Future<AssistantSettingsData> _future;

  final _keyControllers = <String, TextEditingController>{
    'gemini': TextEditingController(),
    'groq': TextEditingController(),
    'cloudflare': TextEditingController(),
    'openrouter': TextEditingController(),
  };
  final _cloudflareAccountController = TextEditingController();
  final _obscure = <String, bool>{
    'gemini': true,
    'groq': true,
    'cloudflare': true,
    'openrouter': true,
  };

  String? _savingProvider;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    for (final controller in _keyControllers.values) {
      controller.dispose();
    }
    _cloudflareAccountController.dispose();
    super.dispose();
  }

  Future<AssistantSettingsData> _load() {
    return ref.read(assistantSettingsRepositoryProvider).fetch();
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _saveProvider(String provider) async {
    if (_savingProvider != null) return;
    final key = _keyControllers[provider]!.text.trim();
    if (key.isEmpty) {
      _showMessage('Enter the ${_label(provider)} API key first.');
      return;
    }

    final accountId = provider == 'cloudflare'
        ? _cloudflareAccountController.text.trim()
        : null;

    setState(() => _savingProvider = provider);
    try {
      await ref.read(assistantSettingsRepositoryProvider).testAndSaveProvider(
            provider,
            key,
            accountId: accountId,
          );
      _keyControllers[provider]!.clear();
      if (provider == 'cloudflare') {
        _cloudflareAccountController.clear();
      }
      if (!mounted) return;
      _showMessage('${_label(provider)} credentials tested and saved securely.');
      await _reload();
    } on ApiException catch (error) {
      if (mounted) _showMessage(error.message);
    } catch (_) {
      if (mounted) _showMessage('Could not save ${_label(provider)} credentials.');
    } finally {
      if (mounted) setState(() => _savingProvider = null);
    }
  }

  Future<void> _confirmDeleteProvider(String provider) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${_label(provider)} credentials?'),
        content: Text(
          '${_label(provider)} will no longer be used by the Assistant fallback chain.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _savingProvider = provider);
    try {
      await ref.read(assistantSettingsRepositoryProvider).deleteProvider(provider);
      if (!mounted) return;
      _showMessage('${_label(provider)} credentials removed.');
      await _reload();
    } finally {
      if (mounted) setState(() => _savingProvider = null);
    }
  }

  String _label(String provider) {
    switch (provider) {
      case 'gemini':
        return 'Gemini';
      case 'groq':
        return 'Groq';
      case 'cloudflare':
        return 'Cloudflare Workers AI';
      case 'openrouter':
        return 'OpenRouter';
      default:
        return provider;
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.of(context).background,
        elevation: 0,
        title: const Text('Settings'),
      ),
      body: FutureBuilder<AssistantSettingsData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting &&
              !snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.hasData) return _errorView();
          return RefreshIndicator(
            onRefresh: _reload,
            child: _content(snapshot.data!, themeMode),
          );
        },
      ),
    );
  }

  Widget _content(AssistantSettingsData data, ThemeMode themeMode) {
    final colors = AppColors.of(context);
    const priority = ['gemini', 'groq', 'cloudflare', 'openrouter'];

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 50),
      children: [
        const Text(
          'Appearance',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 5),
        Text(
          'Choose how AI Task Manager looks.',
          style: TextStyle(color: colors.textSecondary, fontSize: 12),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 11),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(15),
            border: Border.all(color: colors.border),
          ),
          child: Row(
            children: [
              Icon(Icons.dark_mode_outlined, color: colors.textSecondary),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Dark mode', style: TextStyle(fontWeight: FontWeight.w600)),
                    SizedBox(height: 2),
                    Text('Use the dark app appearance', style: TextStyle(fontSize: 11)),
                  ],
                ),
              ),
              Switch(
                value: themeMode == ThemeMode.dark,
                onChanged: (enabled) {
                  ref.read(themeModeProvider.notifier).setMode(
                        enabled ? ThemeMode.dark : ThemeMode.light,
                      );
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 30),
        const Text(
          'AI Providers',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 5),
        Text(
          'Keys are stored securely on this device. Text and task parsing automatically move to the next configured provider when the current provider is rate-limited or unavailable.',
          style: TextStyle(color: colors.textSecondary, fontSize: 12, height: 1.4),
        ),
        const SizedBox(height: 14),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: colors.surfaceElevated,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.swap_vert_circle_outlined, size: 19),
                  SizedBox(width: 8),
                  Text('Automatic fallback', style: TextStyle(fontWeight: FontWeight.w700)),
                  Spacer(),
                  Text('ON', style: TextStyle(fontWeight: FontWeight.w700)),
                ],
              ),
              const SizedBox(height: 9),
              Text(
                'Priority: Gemini → Groq → Cloudflare → OpenRouter Free',
                style: TextStyle(color: colors.textSecondary, fontSize: 11, height: 1.4),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        for (final name in priority) ...[
          _providerCard(data.provider(name)!),
          const SizedBox(height: 12),
        ],
        _InfoCard(
          icon: Icons.psychology_outlined,
          title: 'Reasoning',
          subtitle: 'Task execution remains deterministic after AI interpretation',
          value: 'Automatic',
          valueColor: colors.textPrimary,
        ),
        if (data.message.isNotEmpty) ...[
          const SizedBox(height: 18),
          Text(
            data.message,
            style: TextStyle(color: colors.textSecondary, fontSize: 11, height: 1.4),
          ),
        ],
      ],
    );
  }

  Widget _providerCard(AssistantProviderSettings item) {
    final colors = AppColors.of(context);
    final busy = _savingProvider == item.provider;
    final controller = _keyControllers[item.provider]!;

    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(item.model, style: TextStyle(color: colors.textSecondary, fontSize: 10)),
                  ],
                ),
              ),
              if (item.configured)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.check_circle_outline, size: 17, color: AppColors.green),
                    const SizedBox(width: 5),
                    Text(item.keyHint ?? '****', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                    IconButton(
                      tooltip: 'Delete credentials',
                      onPressed: _savingProvider != null ? null : () => _confirmDeleteProvider(item.provider),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                      icon: Icon(Icons.delete_outline, size: 17, color: Theme.of(context).colorScheme.error),
                    ),
                  ],
                )
              else
                Text('Not configured', style: TextStyle(color: colors.textMuted, fontSize: 11)),
            ],
          ),
          if (item.provider == 'gemini') ...[
            const SizedBox(height: 6),
            Text(
              'Gemini is also used by Live Voice.',
              style: TextStyle(color: colors.textSecondary, fontSize: 10),
            ),
          ],
          const SizedBox(height: 12),
          if (item.requiresAccountId) ...[
            TextField(
              controller: _cloudflareAccountController,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                hintText: item.accountId == null
                    ? 'Cloudflare Account ID'
                    : 'Account ID saved: ${_accountHint(item.accountId!)}',
                prefixIcon: const Icon(Icons.badge_outlined),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
              ),
            ),
            const SizedBox(height: 10),
          ],
          TextField(
            controller: controller,
            obscureText: _obscure[item.provider] ?? true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              hintText: item.configured ? 'Enter a new key to replace it' : 'Enter API key / token',
              prefixIcon: const Icon(Icons.key_outlined),
              suffixIcon: IconButton(
                onPressed: () => setState(() {
                  _obscure[item.provider] = !(_obscure[item.provider] ?? true);
                }),
                icon: Icon(
                  (_obscure[item.provider] ?? true)
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                ),
              ),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _savingProvider != null ? null : () => _saveProvider(item.provider),
              child: Text(busy ? 'Checking...' : 'Test & save'),
            ),
          ),
        ],
      ),
    );
  }

  String _accountHint(String accountId) {
    if (accountId.length <= 8) return accountId;
    return '${accountId.substring(0, 4)}…${accountId.substring(accountId.length - 4)}';
  }

  Widget _errorView() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 38, color: AppColors.of(context).textMuted),
          const SizedBox(height: 12),
          const Text('Could not load settings.'),
          const SizedBox(height: 12),
          TextButton(onPressed: _reload, child: const Text('Try again')),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final String value;
  final Color valueColor;

  const _InfoCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: colors.textSecondary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(subtitle, style: TextStyle(color: colors.textSecondary, fontSize: 10)),
              ],
            ),
          ),
          Text(value, style: TextStyle(color: valueColor, fontSize: 11, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
''')

# Patch assistant repository: normal assistant gets all provider headers; Live stays Gemini-only.
p = F / 'lib/features/assistant/data/assistant_repository.dart'
text = p.read_text(encoding='utf-8')
text = text.replace(
'    final headers = await _geminiHeaders();\n    final result = await _apiClient.post(\n      \'/api/assistant/chat\'',
'    final headers = await _providerHeaders();\n    final result = await _apiClient.post(\n      \'/api/assistant/chat\'',
1,
)
text = text.replace(
'    final headers = await _geminiHeaders();\n    final payload = <String, dynamic>{',
'    final headers = await _providerHeaders();\n    final payload = <String, dynamic>{',
1,
)
marker = '''  Future<Map<String, dynamic>> _geminiHeaders() async {\n    final apiKey = await _keyStore.read();\n    if (apiKey == null) {\n      throw const ApiException(\n        message: 'Add your Gemini API key in Settings first.',\n      );\n    }\n    return {'X-Gemini-Api-Key': apiKey};\n  }\n'''
replacement = marker + r'''

  Future<Map<String, dynamic>> _providerHeaders() async {
    final headers = <String, dynamic>{};

    final gemini = await _keyStore.readProviderApiKey('gemini');
    final groq = await _keyStore.readProviderApiKey('groq');
    final cloudflare = await _keyStore.readProviderApiKey('cloudflare');
    final cloudflareAccountId = await _keyStore.readCloudflareAccountId();
    final openrouter = await _keyStore.readProviderApiKey('openrouter');

    if (gemini != null) headers['X-Gemini-Api-Key'] = gemini;
    if (groq != null) headers['X-Groq-Api-Key'] = groq;
    if (cloudflare != null && cloudflareAccountId != null) {
      headers['X-Cloudflare-Api-Token'] = cloudflare;
      headers['X-Cloudflare-Account-Id'] = cloudflareAccountId;
    }
    if (openrouter != null) headers['X-OpenRouter-Api-Key'] = openrouter;

    if (headers.isEmpty) {
      throw const ApiException(
        message: 'Add at least one AI provider API key in Settings first.',
      );
    }

    return headers;
  }
'''
if marker not in text:
    raise RuntimeError('assistant repository header marker not found')
text = text.replace(marker, replacement, 1)
p.write_text(text, encoding='utf-8')
print('PATCHED', p)

print('DONE')
