"""Multi-provider assistant service.

Cloud models interpret chat/task language. Draft validation, confirmation,
execution and persistence remain deterministic backend concerns.
"""

import re

from src.modules.assistant.drafts.service import (
    execute_task_draft,
    preview_task_draft,
    select_draft_target,
)
from src.modules.assistant.prompts.chat_prompt import CHAT_SYSTEM_PROMPT
from src.modules.assistant.providers.provider_registry import get_provider_spec
from src.modules.assistant.providers.provider_router import (
    chat_with_fallback,
    provider_health,
)


_RUNTIME_IDENTITY_PATTERNS = (
    re.compile(
        r"^(?:what|which)\s+(?:ai|ai\s+model|model|provider)"
        r"(?:\s+(?:are|is)\s+(?:you|this))?(?:\s+using)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:what|which)\s+(?:ai|ai\s+model|model|provider)"
        r"\s+(?:do|does)\s+(?:you|this)\s+use$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:what|which)\s+(?:ai|model|provider)"
        r"\s+(?:is\s+)?(?:running|active|answering|being\s+used)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:are\s+you|is\s+this)\s+(?:using\s+)?"
        r"(?:gemini|groq|cloudflare|openrouter|cerebras|mistral|nvidia)"
        r"(?:\s+ai)?$",
        re.IGNORECASE,
    ),
)


def _normalize_identity_question(message):
    text = str(message or "").strip().lower()
    text = re.sub(r"[^a-z0-9@./_-]+", " ", text)
    return " ".join(text.split())


def _is_runtime_identity_question(message):
    text = _normalize_identity_question(message)
    if not text:
        return False

    if text in {
        "which ai",
        "what ai",
        "which model",
        "what model",
        "which provider",
        "what provider",
        "which ai is this",
        "what ai is this",
        "which model is this",
        "what model is this",
        "which provider is this",
        "what provider is this",
    }:
        return True

    return any(
        pattern.fullmatch(text)
        for pattern in _RUNTIME_IDENTITY_PATTERNS
    )


def _provider_label(provider_name):
    try:
        return get_provider_spec(provider_name).label
    except (TypeError, ValueError):
        value = str(provider_name or "").strip()
        return value or "AI provider"


def _authoritative_identity_reply(routed):
    provider_name = str(routed.get("provider") or "").strip()
    provider_label = _provider_label(provider_name)
    model = str(routed.get("model") or "").strip() or "Unknown"
    fallback_used = bool(routed.get("fallback_used"))

    lines = [
        "You are currently using:",
        f"Provider: {provider_label}",
        f"Model: {model}",
        f"Fallback: {'Yes' if fallback_used else 'No'}",
    ]

    attempted = routed.get("attempted_providers") or []
    if fallback_used and isinstance(attempted, (list, tuple)):
        attempted_labels = [
            _provider_label(name)
            for name in attempted
            if str(name or "").strip()
        ]
        if len(attempted_labels) > 1:
            lines.append(
                "Route: " + " -> ".join(attempted_labels)
            )

    return "\n".join(lines)


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

    reply = routed["result"]

    # Provider/model identity is runtime routing metadata, not something
    # the language model can reliably self-report. The request still goes
    # through the normal router first so fallback/provider/model reflect
    # the provider that actually handled this request.
    if _is_runtime_identity_question(message):
        reply = _authoritative_identity_reply(routed)

    return {
        "provider": routed["provider"],
        "type": routed["type"],
        "model": routed["model"],
        "reply": reply,
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
