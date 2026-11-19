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

from app.core.timezones import user_today
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
from app.features.assistant.replies import is_no, is_number_reply, is_yes, parse_choice
from app.features.tasks.models import TaskCategory, TaskStatus
from app.features.tasks.service import NewDueDateRequired, get_task, list_tasks

logger = logging.getLogger("assistant")

_EXECUTORS = {
    Intent.CREATE_TASK: dispatcher.execute_create_task,
    Intent.UPDATE_TASK: dispatcher.execute_update_task,
    Intent.CHANGE_PRIORITY: dispatcher.execute_change_priority,
    Intent.DELETE_TASK: dispatcher.execute_delete_task,
    Intent.COMPLETE_TASK: dispatcher.execute_complete_task,
    Intent.RETRIEVE_TASKS: dispatcher.execute_retrieve_tasks,
    Intent.RETRIEVE_STATS: dispatcher.execute_retrieve_stats,
    Intent.CONFIGURE_REMINDER: dispatcher.execute_configure_reminder,
    Intent.PAUSE_TASK: dispatcher.execute_pause_task,
    Intent.RESUME_TASK: dispatcher.execute_resume_task,
}

# What to ask when a required detail is missing (the first missing one is asked).
_QUESTIONS = {
    "title": "What's the title?",
    "day_selection": "Which days should it repeat on? (for example: every day, weekdays, or Mon/Wed/Fri)",
    "weekdays": "Which days of the week?",
    "times": "At what time should I remind you?",
    "end_date": "Until which date should the reminders run?",
    "due_date": "The due date passed while it was paused. What's the new due date?",
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


def _missing_required(pending: PendingAction) -> list[str]:
    """Details still needed before asking for confirmation (Python decides,
    not Gemini). Checked after every turn, so answers fill them one by one."""
    intent, missing = pending.intent, []
    if intent not in (Intent.RETRIEVE_TASKS, Intent.RETRIEVE_STATS) and not pending.title:
        missing.append("title")
    schedules = (intent == Intent.CREATE_TASK and pending.category == "recurring") or intent == Intent.CONFIGURE_REMINDER
    if schedules:
        if not pending.day_selection:
            missing.append("day_selection")
        elif pending.day_selection == "custom_weekdays" and not pending.weekdays:
            missing.append("weekdays")
    if intent == Intent.CONFIGURE_REMINDER and not pending.times:
        missing.append("times")
    return missing


def _due_text(pending: PendingAction) -> str:
    if not pending.due_date:
        return ""
    return f", due {pending.due_date}" + (f" at {pending.due_time.strftime('%H:%M')}" if pending.due_time else "")


def _confirmation_message(pending: PendingAction, today) -> str:
    if pending.intent == Intent.CREATE_TASK:
        if pending.category == "recurring":
            return (f'Create recurring task "{pending.title}": '
                    f"{dispatcher.describe_schedule(pending, today)}. Confirm?")
        reminder = ""
        if pending.times:
            end = pending.due_date or pending.start_date or today
            reminder = f", reminders {dispatcher.describe_schedule(pending.model_copy(update={'end_date': end}), today)}"
        return f'Create a one-time task "{pending.title}"{_due_text(pending)}{reminder}. Confirm?'
    if pending.intent == Intent.CONFIGURE_REMINDER:
        return (f'Set reminders for "{pending.title}": {dispatcher.describe_schedule(pending, today)}. '
                f"This replaces its current reminder schedule. Confirm?")
    if pending.intent == Intent.PAUSE_TASK:
        return f'Pause "{pending.title}" (its reminders stop until you resume it). Confirm?'
    if pending.intent == Intent.RESUME_TASK:
        new_due = f" with new due date {pending.due_date}" if pending.due_date else ""
        return f'Resume "{pending.title}"{new_due}. Confirm?'
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


# Words sharing at least this many leading letters are treated as the same
# word ("meditation"/"meditate", "updating"/"update") — the endings English
# stemming can't line up. Short words must match exactly.
_SHARED_PREFIX = 5


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < _SHARED_PREFIX:
        return False
    return a[:_SHARED_PREFIX] == b[:_SHARED_PREFIX]


def _match_tasks(tasks: list, query: str) -> list:
    """Deterministic task lookup (no AI). 1) titles containing the query text;
    if none, 2) titles containing every key word of the query, after removing
    filler words, stemming and shared 5-letter beginnings — so "feeding the
    cat" finds "Feed the cat", "passport wala task" finds "Renew passport"
    and "meditation" finds "meditate". Several hits -> the caller asks the
    user to pick; it never guesses."""
    active = [t for t in tasks if t.status != TaskStatus.CANCELLED]
    needle = query.strip().lower()
    exact = [t for t in active if needle in t.title.lower()]
    if exact:
        return exact
    wanted = _key_words(query)
    if not wanted:
        return []
    return [t for t in active if all(any(_same_word(w, tw) for tw in _key_words(t.title)) for w in wanted)]


async def _find_task_by_title(db: AsyncSession, user_id: uuid.UUID, title: str) -> list:
    return _match_tasks(await list_tasks(db, user_id), title)


_MERGED_FIELDS = ("title", "new_title", "urgent", "important", "due_date", "due_time", "category",
                  "day_selection", "start_date", "end_date", "weekdays", "times")


def _apply_gemini_output(pending: PendingAction, parsed: GeminiIntentOutput) -> PendingAction:
    """Merges this turn's extraction into what's already known: a value
    Gemini left empty never erases one the user gave earlier."""
    data = pending.model_dump()
    for field in _MERGED_FIELDS:
        value = getattr(parsed, field)
        if value is not None and value != []:
            data[field] = value
    data["intent"] = parsed.intent
    return PendingAction(**data)


def _jsonable(value):
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value.isoformat() if hasattr(value, "isoformat") else value


async def _build_prompt(message: str, pending: PendingAction, today=None) -> str:
    """`today` is the USER'S local date, so \"tomorrow\" resolves in their zone
    (defaults to today in the default zone, for scripts that build prompts)."""
    from app.core.timezones import default_zone, today_in

    today = today or today_in(default_zone())

    known = {
        k: _jsonable(v)
        for k, v in pending.model_dump().items()
        if k in _MERGED_FIELDS and v not in (None, [])
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
            if field in ("day_selection", "weekdays"):
                context += 'For specific days use day_selection="custom_weekdays" plus weekdays.\n'

    return f"""You are a task-manager assistant. Extract structured intent from the user's
message and return ONLY a JSON object, no markdown, no explanation, matching exactly:

{{
  "intent": one of ["create_task","update_task","delete_task","complete_task","change_priority","retrieve_tasks","retrieve_stats","configure_reminder","pause_task","resume_task","unknown"],
  "title": string or null,       // the task's name, for any intent referring to a specific task
  "new_title": string or null,   // only for update_task when renaming
  "category": "one_time" or "recurring" or null,  // create_task only: "recurring" if it repeats
  "urgent": true/false or null,
  "important": true/false or null,
  "due_date": "YYYY-MM-DD" or null,  // one-time deadline; resolve relative dates using today's date below
  "due_time": "HH:MM" or null,       // one-time deadline time, 24-hour
  "day_selection": "every_day" | "weekdays" | "weekends" | "custom_weekdays" | null,  // which days it repeats / reminds
  "weekdays": [numbers],             // only with custom_weekdays: 1=Monday 2=Tuesday ... 7=Sunday
  "start_date": "YYYY-MM-DD" or null,  // only if the user says when it starts
  "end_date": "YYYY-MM-DD" or null,    // only if the user says when it ends
  "times": ["HH:MM", ...],           // reminder times of day, 24-hour (7am -> "07:00", 6:30pm -> "18:30")
  "missing_fields": []               // field names above you could not determine but the intent needs
}}

How to choose the intent:
- create_task ONLY when the user wants a NEW task ("add", "create", "new task", "remind me to...").
- A message about an EXISTING task by name is never create_task:
  - "make X urgent", "X is important", "mark X as not urgent", "prioritize X" -> change_priority
  - "rename X to Y", "change X's title" -> update_task (title=X, new_title=Y)
  - "mark X as done", "finished X", "complete X" -> complete_task
  - "delete X", "remove X" -> delete_task
  - "remind me about X at <time>", "set a reminder for X", "X reminders every <days>" -> configure_reminder (title=X)
  - "pause X", "put X on hold" -> pause_task;  "resume X", "unpause X", "start X again" -> resume_task
- A NEW task that repeats ("daily", "every day", "on weekdays", "every Tuesday and Thursday", "each Sunday")
  -> create_task with category "recurring", day_selection, weekdays (if specific days) and times (if a time is said).
  Keep the days and times OUT of the title.
- A NEW task that happens once -> category "one_time"; a deadline goes in due_date/due_time.
- The user may write in any language (e.g. Hindi/Hinglish); keep the task title in the user's words.

Today's date is {today.isoformat()}.
{context}
Never invent a value you're not confident about — use null and list it in missing_fields instead.
If the message doesn't match a supported task-management operation, use intent "unknown".

User message: {message!r}"""


async def _ask(user_id: uuid.UUID, pending: PendingAction, missing: list[str]) -> AssistantMessageResponse:
    pending.state = ConversationState.COLLECTING_INFORMATION
    pending.missing_fields = missing
    await conversation_state.set_pending(user_id, pending)
    return AssistantMessageResponse(reply=_QUESTIONS.get(missing[0], f"What's the {missing[0]}?"), state=pending.state)


async def _confirm(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> AssistantMessageResponse:
    pending.state = ConversationState.AWAITING_CONFIRMATION
    pending.missing_fields = []
    await conversation_state.set_pending(user_id, pending)
    reply = _confirmation_message(pending, await user_today(db, user_id))

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


async def _after_task_chosen(db: AsyncSession, user_id: uuid.UUID, pending: PendingAction) -> AssistantMessageResponse:
    """The task is known (pending.task_id). Fill details that depend on it,
    ask for anything still missing, otherwise ask for confirmation."""
    if pending.intent == Intent.CONFIGURE_REMINDER and pending.end_date is None:
        task = await get_task(db, pending.task_id, user_id)
        if task.category == TaskCategory.ONE_TIME:
            pending.end_date = task.due_date  # remind until it's due
            if pending.end_date is None:
                return await _ask(user_id, pending, ["end_date"])
    return await _confirm(db, user_id, pending)


async def handle_message(
    db: AsyncSession, user_id: uuid.UUID, message: str, input_mode: str = "text"
) -> AssistantMessageResponse:
    """One user turn. Text and voice (the phone's speech-to-text) take
    exactly the same path; `input_mode` is only logged."""
    logger.info("assistant message via %s", input_mode)
    pending = await conversation_state.get_pending(user_id)

    # --- Rule-based shortcuts (MSI level 1 — no Gemini call) ---
    if pending.state == ConversationState.AWAITING_CONFIRMATION:
        if is_yes(message):
            executor = _EXECUTORS[pending.intent]
            try:
                reply = await executor(db, user_id, pending)
            except NewDueDateRequired:
                # Resuming a one-time task whose due date passed while it was
                # paused: ask for a new date, keep the request going.
                await db.rollback()
                pending.due_date, pending.due_time = None, None
                return await _ask(user_id, pending, ["due_date"])
            except (NotFoundError, DomainValidationError) as exc:
                # e.g. the task was deleted between "Confirm?" and "yes" —
                # tell the user instead of surfacing a 500.
                logger.info("Confirmed assistant action could not run: %s", exc)
                await db.rollback()  # nothing half-done is kept
                reply = f"Couldn't do that: {exc}"
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply=reply, state=ConversationState.IDLE)
        if is_no(message):
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply="Cancelled.", state=ConversationState.IDLE)
        # Anything else invalidates the pending confirmation (spec: a modified
        # request must not reuse a stale confirmation) — even "yes, but at
        # 8am" — and is processed as a brand-new message.
        await conversation_state.clear_pending(user_id)
        pending = PendingAction(state=ConversationState.IDLE)

    elif pending.state == ConversationState.AWAITING_TASK_SELECTION:
        if is_no(message):
            await conversation_state.clear_pending(user_id)
            return AssistantMessageResponse(reply="Cancelled.", state=ConversationState.IDLE)

        options = "\n".join(f"{i+1}) {c['title']}" for i, c in enumerate(pending.candidates))
        number = parse_choice(message, len(pending.candidates))
        if number is not None:
            choice = pending.candidates[number - 1]
        elif is_number_reply(message):
            # A number/ordinal that doesn't fit: re-ask rather than treat it
            # as a brand-new request.
            return AssistantMessageResponse(
                reply=f"Please pick a number from 1 to {len(pending.candidates)}:\n{options}",
                state=ConversationState.AWAITING_TASK_SELECTION,
            )
        else:
            text = message.strip().lower()
            matches = [c for c in pending.candidates if text and text in c["title"].lower()]
            choice = matches[0] if len(matches) == 1 else None

        if choice is not None:
            pending.task_id = choice["id"]
            pending.title = choice["title"]  # confirm with the real name, not the search text
            pending.candidates = []
            return await _after_task_chosen(db, user_id, pending)

        # Not a pick: the user moved on ("actually, delete X instead", a new
        # question...). Drop the selection and treat it as a fresh message.
        await conversation_state.clear_pending(user_id)
        pending = PendingAction(state=ConversationState.IDLE)

    # "no"/"cancel" with nothing to confirm or pick: answer by rule. Cancels
    # an in-progress question ("What's the title?"), else there's nothing to
    # cancel — no reason to ask Gemini (and wait seconds) for this.
    if is_no(message):
        had_request = pending.intent is not None
        await conversation_state.clear_pending(user_id)
        return AssistantMessageResponse(
            reply="Cancelled." if had_request else "Nothing to cancel.",
            state=ConversationState.IDLE,
        )

    # --- Gemini call (fresh message, or filling in missing fields) ---
    prompt = await _build_prompt(message, pending, today=await user_today(db, user_id))
    raw = None
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

    if parsed.intent in UNSUPPORTED_INTENTS:  # pragma: no cover - none at the moment
        return AssistantMessageResponse(
            reply="That isn't supported by the assistant yet — please use the app for that.",
            state=ConversationState.IDLE,
        )

    pending = _apply_gemini_output(pending, parsed)
    if pending.intent == Intent.CREATE_TASK and pending.category is None:
        pending.category = "recurring" if pending.day_selection else "one_time"
    if pending.intent == Intent.CONFIGURE_REMINDER and pending.day_selection is None:
        pending.day_selection = "every_day"  # "remind me about X at 9" names no days: daily

    # Read-only intents execute immediately — no confirmation, nothing written.
    if pending.intent in READ_ONLY_INTENTS:
        reply = await _EXECUTORS[pending.intent](db, user_id, pending)
        return AssistantMessageResponse(reply=reply, state=ConversationState.IDLE)

    missing = _missing_required(pending)
    if missing:
        return await _ask(user_id, pending, missing)

    # For intents that act on an EXISTING task, resolve the title to a real task first.
    if pending.intent in LOOKUP_INTENTS:
        matches = await _find_task_by_title(db, user_id, pending.title)
        if not matches and pending.intent == Intent.CONFIGURE_REMINDER:
            # "Remind me to X ..." is often a NEW task that Gemini read as a
            # reminder on an existing one. Nothing by that name exists, so
            # offer to create it — still only after the user confirms.
            pending.intent = Intent.CREATE_TASK
            pending.category = "one_time" if pending.due_date else "recurring"
            missing = _missing_required(pending)
            if missing:
                return await _ask(user_id, pending, missing)
            response = await _confirm(db, user_id, pending)
            response.reply = f"There's no task called \"{pending.title}\" yet, so I'll create it. " + response.reply
            return response
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
        return await _after_task_chosen(db, user_id, pending)

    return await _confirm(db, user_id, pending)
