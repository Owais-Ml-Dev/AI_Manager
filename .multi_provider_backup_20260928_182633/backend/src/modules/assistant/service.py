"""Gemini-only assistant service.

Gemini handles chat and structured task parsing.  Draft validation, duplicate
matching, execution, and persistence remain deterministic backend concerns.
"""

from src.modules.assistant.drafts.service import (
    execute_task_draft,
    preview_task_draft,
    select_draft_target,
)
from src.modules.assistant.prompts.chat_prompt import CHAT_SYSTEM_PROMPT
from src.modules.assistant.providers.provider_factory import create_provider


def get_assistant_status(api_key=None):
    return create_provider(api_key=api_key).health()


def send_chat(message, api_key=None):
    provider = create_provider(api_key=api_key)
    reply = provider.chat(message=message, system_prompt=CHAT_SYSTEM_PROMPT)
    return {
        "provider": "gemini",
        "type": "api",
        "model": getattr(provider, "model_used", provider.model),
        "reply": reply,
    }


def preview_task_command(
    message,
    timezone_name="UTC",
    api_key=None,
    draft_id=None,
):
    return preview_task_draft(
        message=message,
        timezone_name=timezone_name,
        api_key=api_key,
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
