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
import re
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.gemini import (
    GeminiError,
    GeminiQuotaExhaustedError,
    GeminiUnavailableError,
    generate_json,
)
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
from app.common.exceptions import NotFoundError
from app.common.exceptions import ValidationError as DomainValidationError
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


def _wait_phrase(available_at) -> str:
    """'in about 40 minutes' — relative, because the app has no per-user
    timezone yet (a clock time would be in the server's zone)."""
    from datetime import datetime, timezone

    seconds = max(0, (available_at - datetime.now(timezone.utc)).total_seconds())
    if seconds < 90:
        return "in about a minute"
    if seconds < 90 * 60:
        return f"in about {round(seconds / 60)} minutes"
    return f"in about {round(seconds / 3600)} hours"


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


# Words people add around a task's name ("the passport task", "passport wala
# task", "my gym one") that are not part of the name itself.
_FILLER_WORDS = {
    "a", "an", "the", "my", "this", "that", "task", "tasks", "one", "item", "todo",
    "please", "wala", "wali", "wale", "vala", "vali", "ka", "ki", "ke", "to", "for", "of",
}


def _stem(word: str) -> str:
    """Crude, predictable suffix stripping so "feeding"/"feeds" match "feed".
    Deliberately simple: applied identically to query and titles, and
    repeated until stable so "meetings" and "meeting" both reach "meet"."""
    changed = True
    while changed:
        changed = False
        for suffix in ("ing", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                changed = True
                break
    return word


def _key_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _FILLER_WORDS}


def _match_tasks(tasks: list, query: str) -> list:
    """Deterministic task lookup (no AI). 1) titles containing the query text;
    if none, 2) titles containing every key word of the query, after removing
    filler words and stemming — so "feeding the cat" finds "Feed the cat" and
    "passport wala task" finds "Renew passport". Several hits -> the caller
    asks the user to pick; it never guesses."""
    active = [t for t in tasks if t.status != TaskStatus.CANCELLED]
    needle = query.strip().lower()
    exact = [t for t in active if needle in t.title.lower()]
    if exact:
        return exact
    wanted = _key_words(query)
    if not wanted:
        return []
    return [t for t in active if wanted <= _key_words(t.title)]


async def _find_task_by_title(db: AsyncSession, user_id: uuid.UUID, title: str) -> list:
    return _match_tasks(await list_tasks(db, user_id), title)


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
                f"with no task-management keywords in it (e.g. a reply of just \"Pay rent\" "
                f"or \"name it Pay rent\" to a question about the title means "
                f'title=\\"Pay rent\\"). Keep intent as \'{pending.intent.value}\'.\n'
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

How to choose the intent:
- create_task ONLY when the user wants a NEW task ("add", "create", "new task", "remind me to...").
- A message about an EXISTING task by name is never create_task:
  - "make X urgent", "X is important", "mark X as not urgent", "prioritize X" -> change_priority
  - "rename X to Y", "change X's title" -> update_task (title=X, new_title=Y)
  - "mark X as done", "finished X", "complete X" -> complete_task
  - "delete X", "remove X" -> delete_task
- The user may write in any language (e.g. Hindi/Hinglish); keep the task title in the user's words.

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
            except (NotFoundError, DomainValidationError) as exc:
                # e.g. the task was deleted between "Confirm?" and "yes" —
                # tell the user instead of surfacing a 500.
                logger.info("Confirmed assistant action could not run: %s", exc)
                reply = f"Couldn't do that: {exc}"
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
        if text in _NO_WORDS:
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply="Cancelled.", state=ConversationState.IDLE)

        if text.isdigit():
            # A number is always a pick — re-ask if it's out of range rather
            # than sending a bare number to Gemini as a new request.
            if 1 <= int(text) <= len(pending.candidates):
                choice = pending.candidates[int(text) - 1]
            else:
                options = "\n".join(f"{i+1}) {c['title']}" for i, c in enumerate(pending.candidates))
                return AssistantMessageResponse(
                    reply=f"Please pick a number from 1 to {len(pending.candidates)}:\n{options}",
                    state=ConversationState.AWAITING_TASK_SELECTION,
                )
        else:
            matches = [c for c in pending.candidates if text in c["title"].lower()]
            choice = matches[0] if len(matches) == 1 else None

        if choice is not None:
            pending.task_id = choice["id"]
            pending.title = choice["title"]  # confirm with the real name, not the search text
            pending.candidates = []
            pending.state = ConversationState.AWAITING_CONFIRMATION
            await conversation_state.set_pending(user_id, pending)
            return AssistantMessageResponse(
                reply=_confirmation_message(pending), state=pending.state
            )

        # Not a pick: the user moved on ("actually, delete X instead", a new
        # question...). Drop the selection and treat it as a fresh message —
        # same rule as a modified request during confirmation. Previously this
        # re-asked forever, trapping the user until the state expired.
        await conversation_state.clear_pending(user_id)
        pending = PendingAction(state=ConversationState.IDLE)

    # "no"/"cancel" with nothing to confirm or pick: answer by rule. Cancels
    # an in-progress question ("What's the title?"), else there's nothing to
    # cancel — no reason to ask Gemini (and wait seconds) for this.
    if text in _NO_WORDS:
        had_request = pending.intent is not None
        await conversation_state.clear_pending(user_id)
        return AssistantMessageResponse(
            reply="Cancelled." if had_request else "Nothing to cancel.",
            state=ConversationState.IDLE,
        )

    # --- Gemini call (fresh message, or filling in missing fields) ---
    prompt = await _build_prompt(message, pending)
    try:
        raw = await generate_json(prompt)
        parsed = GeminiIntentOutput.model_validate(raw)
    except GeminiQuotaExhaustedError as exc:
        # Every model in the fallback chain is out of free quota. Say when it
        # comes back; keep any in-progress request for then.
        logger.warning("All Gemini models out of quota: %s", exc)
        return AssistantMessageResponse(
            reply=f"The assistant has reached its usage limit for now. "
                  f"It will be available again {_wait_phrase(exc.available_at)}.",
            state=pending.state,
        )
    except GeminiUnavailableError as exc:
        # Gemini down/slow: not the user's wording, so don't ask them to
        # rephrase. Any in-progress request is kept for their retry.
        logger.warning("Gemini unavailable, degrading gracefully: %s", exc)
        return AssistantMessageResponse(
            reply="The assistant is busy right now. Please try again in a moment.",
            state=pending.state,
        )
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
        pending.title = matches[0].title  # confirm with the real name, not the search text

    pending.state = ConversationState.AWAITING_CONFIRMATION
    await conversation_state.set_pending(user_id, pending)
    reply = _confirmation_message(pending)

    # Deterministic guard against Gemini misreading "make X urgent" as a
    # create: if a task with this exact title already exists, say so before
    # the user confirms, so a duplicate is never created by accident.
    if pending.intent == Intent.CREATE_TASK:
        wanted = pending.title.strip().lower()
        if any(t.title.strip().lower() == wanted for t in await _find_task_by_title(db, user_id, pending.title)):
            reply = (
                f'Note: you already have a task called "{pending.title}". '
                f"If you meant to change it, say no and tell me what to change. " + reply
            )
    return AssistantMessageResponse(reply=reply, state=pending.state)
