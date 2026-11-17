"""The AI conversation state machine (spec section 12).

Rules first (MSI level 1): a plain "yes"/"no" while awaiting confirmation, or
a plain number while awaiting task selection, is handled by Python alone —
no Gemini call. Gemini is only invoked to turn free-text into structured
intent data, and its output is treated as untrusted until Pydantic validates
it against the allowlist in schemas.Intent.

No AI-initiated create/update/delete/complete ever runs without an explicit
confirmation step from this exact pending action — a modified request
invalidates whatever was pending before it.
"""
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.gemini import GeminiError, generate_json
from app.features.assistant import conversation_state, dispatcher
from app.features.assistant.schemas import (
    LOOKUP_INTENTS,
    READ_ONLY_INTENTS,
    UNSUPPORTED_INTENTS,
    AssistantMessageResponse,
    ConversationState,
    GeminiIntentOutput,
    Intent,
    PendingAction,
)
from app.features.tasks.models import TaskStatus
from app.features.tasks.service import list_tasks

logger = logging.getLogger("assistant")

_YES_WORDS = {"yes", "y", "yep", "yeah", "confirm", "correct", "sure", "ok", "okay"}
_NO_WORDS = {"no", "n", "nope", "cancel", "nevermind", "never mind"}

_EXECUTORS = {
    Intent.CREATE_TASK: dispatcher.execute_create_task,
    Intent.UPDATE_TASK: dispatcher.execute_update_task,
    Intent.CHANGE_PRIORITY: dispatcher.execute_change_priority,
    Intent.DELETE_TASK: dispatcher.execute_delete_task,
    Intent.COMPLETE_TASK: dispatcher.execute_complete_task,
    Intent.RETRIEVE_TASKS: dispatcher.execute_retrieve_tasks,
    Intent.RETRIEVE_STATS: dispatcher.execute_retrieve_stats,
}

_REQUIRED_FIELDS = {
    Intent.CREATE_TASK: ["title"],
    Intent.UPDATE_TASK: ["title"],
    Intent.CHANGE_PRIORITY: ["title"],
    Intent.DELETE_TASK: ["title"],
    Intent.COMPLETE_TASK: ["title"],
}


def _missing_required(intent: Intent, pending: PendingAction) -> list[str]:
    return [f for f in _REQUIRED_FIELDS.get(intent, []) if getattr(pending, f, None) is None]


def _confirmation_message(pending: PendingAction) -> str:
    if pending.intent == Intent.CREATE_TASK:
        due = f", due {pending.due_date}" if pending.due_date else ""
        return f'Create a one-time task "{pending.title}"{due}. Confirm?'
    if pending.intent == Intent.DELETE_TASK:
        return f'Delete "{pending.title}". Confirm?'
    if pending.intent == Intent.COMPLETE_TASK:
        return f'Mark "{pending.title}" as completed. Confirm?'
    if pending.intent in (Intent.UPDATE_TASK, Intent.CHANGE_PRIORITY):
        changes = []
        if pending.new_title:
            changes.append(f'rename to "{pending.new_title}"')
        if pending.urgent is not None:
            changes.append(f"urgent={pending.urgent}")
        if pending.important is not None:
            changes.append(f"important={pending.important}")
        return f'Update "{pending.title}" ({", ".join(changes) or "no changes"}). Confirm?'
    return "Confirm?"  # pragma: no cover - all write intents handled above


async def _find_task_by_title(db: AsyncSession, user_id: uuid.UUID, title: str) -> list:
    tasks = await list_tasks(db, user_id)
    needle = title.strip().lower()
    return [t for t in tasks if t.status != TaskStatus.CANCELLED and needle in t.title.lower()]


def _apply_gemini_output(pending: PendingAction, parsed: GeminiIntentOutput) -> PendingAction:
    data = pending.model_dump()
    for field in ("title", "new_title", "urgent", "important", "due_date"):
        value = getattr(parsed, field)
        if value is not None:
            data[field] = value
    data["intent"] = parsed.intent
    return PendingAction(**data)


async def _build_prompt(message: str, pending: PendingAction) -> str:
    from datetime import date

    known = {
        k: v
        for k, v in pending.model_dump().items()
        if k in ("title", "new_title", "urgent", "important", "due_date") and v is not None
    }

    context = ""
    if pending.intent is not None:
        context = (
            f"\nThis continues an in-progress '{pending.intent.value}' request.\n"
            f"Already known so far (merge with, don't discard, unless the new message clearly "
            f"changes them): {known or 'nothing yet'}.\n"
        )
        if pending.missing_fields:
            field = pending.missing_fields[0]
            context += (
                f"You just asked the user for their '{field}', and this message is their direct "
                f"answer to that — extract it as the '{field}' value even if it's a bare phrase "
                f"with no task-management keywords in it (e.g. a reply of just \"Water the plants\" "
                f"or \"call it Water the plants\" to a question about the title means "
                f'title=\\"Water the plants\\"). Keep intent as \'{pending.intent.value}\'.\n'
            )

    return f"""You are a task-manager assistant. Extract structured intent from the user's
message and return ONLY a JSON object, no markdown, no explanation, matching exactly:

{{
  "intent": one of ["create_task","update_task","delete_task","complete_task","change_priority","retrieve_tasks","retrieve_stats","configure_reminder","unknown"],
  "title": string or null,       // the task's name, for any intent referring to a specific task
  "new_title": string or null,   // only for update_task when renaming
  "urgent": true/false or null,
  "important": true/false or null,
  "due_date": "YYYY-MM-DD" or null,  // resolve relative dates using today's date below
  "missing_fields": []           // field names above you could not determine but the intent needs
}}

Today's date is {date.today().isoformat()}.
{context}
Never invent a value you're not confident about — use null and list it in missing_fields instead.
If the message doesn't match a supported task-management operation, use intent "unknown".

User message: {message!r}"""


async def handle_message(db: AsyncSession, user_id: uuid.UUID, message: str) -> AssistantMessageResponse:
    pending = await conversation_state.get_pending(user_id)
    text = message.strip().lower()

    # --- Rule-based shortcuts (MSI level 1 — no Gemini call) ---
    if pending.state == ConversationState.AWAITING_CONFIRMATION:
        if text in _YES_WORDS:
            executor = _EXECUTORS[pending.intent]
            try:
                reply = await executor(db, user_id, pending)
            finally:
                await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply=reply, state=ConversationState.IDLE)
        if text in _NO_WORDS:
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply="Cancelled.", state=ConversationState.IDLE)
        # Anything else invalidates the pending confirmation (spec: a modified
        # request must not reuse a stale confirmation) — fall through to
        # normal processing as a brand-new message.
        await conversation_state.clear_pending(user_id)
        pending = PendingAction(state=ConversationState.IDLE)

    elif pending.state == ConversationState.AWAITING_TASK_SELECTION:
        choice = None
        if text.isdigit() and 1 <= int(text) <= len(pending.candidates):
            choice = pending.candidates[int(text) - 1]
        else:
            matches = [c for c in pending.candidates if text in c["title"].lower()]
            if len(matches) == 1:
                choice = matches[0]
        if choice is None:
            options = "\n".join(f"{i+1}) {c['title']}" for i, c in enumerate(pending.candidates))
            return AssistantMessageResponse(
                reply=f"I'm not sure which one you mean. Please pick a number:\n{options}",
                state=ConversationState.AWAITING_TASK_SELECTION,
            )
        pending.task_id = choice["id"]
        pending.candidates = []
        pending.state = ConversationState.AWAITING_CONFIRMATION
        await conversation_state.set_pending(user_id, pending)
        return AssistantMessageResponse(
            reply=_confirmation_message(pending), state=pending.state
        )

    # --- Gemini call (fresh message, or filling in missing fields) ---
    prompt = await _build_prompt(message, pending)
    try:
        raw = await generate_json(prompt)
        parsed = GeminiIntentOutput.model_validate(raw)
    except GeminiError as exc:
        logger.warning("Gemini call failed, degrading gracefully: %s", exc)
        return AssistantMessageResponse(
            reply="Sorry, I didn't understand that. Could you rephrase?",
            state=ConversationState.IDLE,
        )
    except ValidationError as exc:
        logger.warning("Gemini output failed validation, degrading gracefully: %s raw=%r", exc, raw)
        return AssistantMessageResponse(
            reply="Sorry, I didn't understand that. Could you rephrase?",
            state=ConversationState.IDLE,
        )

    if parsed.intent == Intent.UNKNOWN:
        return AssistantMessageResponse(
            reply="I didn't understand that as a task management request.",
            state=ConversationState.IDLE,
        )

    if parsed.intent in UNSUPPORTED_INTENTS:
        return AssistantMessageResponse(
            reply="Voice-configured reminders aren't supported yet — please use the app for that.",
            state=ConversationState.IDLE,
        )

    pending = _apply_gemini_output(pending, parsed)

    # Read-only intents execute immediately — no confirmation, nothing written.
    if pending.intent in READ_ONLY_INTENTS:
        reply = await _EXECUTORS[pending.intent](db, user_id, pending)
        return AssistantMessageResponse(reply=reply, state=ConversationState.IDLE)

    missing = _missing_required(pending.intent, pending)
    if missing:
        pending.state = ConversationState.COLLECTING_INFORMATION
        pending.missing_fields = missing
        await conversation_state.set_pending(user_id, pending)
        return AssistantMessageResponse(
            reply=f"What's the {missing[0].replace('_', ' ')}?", state=pending.state
        )

    # For intents that act on an EXISTING task, resolve the title to a real task first.
    if pending.intent in LOOKUP_INTENTS:
        matches = await _find_task_by_title(db, user_id, pending.title)
        if not matches:
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(
                reply=f'I couldn\'t find a task matching "{pending.title}".',
                state=ConversationState.IDLE,
            )
        if len(matches) > 1:
            pending.candidates = [{"id": t.id, "title": t.title} for t in matches]
            pending.state = ConversationState.AWAITING_TASK_SELECTION
            await conversation_state.set_pending(user_id, pending)
            options = "\n".join(f"{i+1}) {t.title}" for i, t in enumerate(matches))
            return AssistantMessageResponse(
                reply=f"Which task did you mean?\n{options}", state=pending.state
            )
        pending.task_id = matches[0].id

    pending.state = ConversationState.AWAITING_CONFIRMATION
    await conversation_state.set_pending(user_id, pending)
    return AssistantMessageResponse(reply=_confirmation_message(pending), state=pending.state)
