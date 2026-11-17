"""The structured contract between Gemini and the backend.

Gemini must return exactly this shape. Pydantic validates it — an unknown
intent value is a validation error, not something the backend improvises
around. Gemini generates intent data; Python executes authorized operations.
"""
import enum
from datetime import date

from pydantic import BaseModel, ConfigDict


class Intent(str, enum.Enum):
    """The explicit allowlist. Nothing outside this list can be dispatched
    to a backend function, no matter what Gemini returns."""

    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    COMPLETE_TASK = "complete_task"
    CHANGE_PRIORITY = "change_priority"
    RETRIEVE_TASKS = "retrieve_tasks"
    RETRIEVE_STATS = "retrieve_stats"
    CONFIGURE_REMINDER = "configure_reminder"  # recognized but not yet executable via voice
    UNKNOWN = "unknown"


READ_ONLY_INTENTS = {Intent.RETRIEVE_TASKS, Intent.RETRIEVE_STATS}
# Intents that need an existing task located by title before anything else.
LOOKUP_INTENTS = {Intent.UPDATE_TASK, Intent.DELETE_TASK, Intent.COMPLETE_TASK, Intent.CHANGE_PRIORITY}
# Recognized by Gemini, but this step doesn't implement execution for them yet.
UNSUPPORTED_INTENTS = {Intent.CONFIGURE_REMINDER}


class GeminiIntentOutput(BaseModel):
    """Gemini's raw output, validated. All fields besides `intent` are
    optional — Gemini must use null/omit rather than invent a value it
    isn't confident about; the backend tracks what's still missing."""

    intent: Intent
    title: str | None = None
    new_title: str | None = None
    urgent: bool | None = None
    important: bool | None = None
    due_date: date | None = None
    missing_fields: list[str] = []


class ConversationState(str, enum.Enum):
    IDLE = "idle"
    COLLECTING_INFORMATION = "collecting_information"
    AWAITING_TASK_SELECTION = "awaiting_task_selection"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class PendingAction(BaseModel):
    """What's persisted in Redis between turns. The DB remains the source of
    truth for everything else — this is purely in-flight conversation state."""

    model_config = ConfigDict(use_enum_values=False)

    state: ConversationState
    intent: Intent | None = None
    title: str | None = None
    new_title: str | None = None
    urgent: bool | None = None
    important: bool | None = None
    due_date: date | None = None
    missing_fields: list[str] = []
    task_id: int | None = None
    candidates: list[dict] = []  # [{"id": int, "title": str}, ...] for task-selection


class AssistantMessageRequest(BaseModel):
    message: str


class AssistantMessageResponse(BaseModel):
    reply: str
    state: ConversationState
