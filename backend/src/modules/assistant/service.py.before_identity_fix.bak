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
