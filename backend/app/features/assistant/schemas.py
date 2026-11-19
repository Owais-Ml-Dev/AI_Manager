"""The structured contract between Gemini and the backend.

Gemini must return exactly this shape. Pydantic validates it — an unknown
intent value is a validation error, not something the backend improvises
around. Gemini generates intent data; Python executes authorized operations.
"""
import enum
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    CONFIGURE_REMINDER = "configure_reminder"  # set/replace an existing task's reminder schedule
    PAUSE_TASK = "pause_task"
    RESUME_TASK = "resume_task"
    UNKNOWN = "unknown"


READ_ONLY_INTENTS = {Intent.RETRIEVE_TASKS, Intent.RETRIEVE_STATS}
# Intents that need an existing task located by title before anything else.
LOOKUP_INTENTS = {
    Intent.UPDATE_TASK, Intent.DELETE_TASK, Intent.COMPLETE_TASK, Intent.CHANGE_PRIORITY,
    Intent.CONFIGURE_REMINDER, Intent.PAUSE_TASK, Intent.RESUME_TASK,
}
# Recognized by Gemini but not executable (none at the moment).
UNSUPPORTED_INTENTS: set[Intent] = set()

# The schedule shapes the assistant can set (the API also has custom_dates).
DaySelection = Literal["every_day", "weekdays", "weekends", "custom_weekdays"]


class _ScheduleFields(BaseModel):
    """Task-type and schedule details, shared by Gemini's output and the
    in-flight conversation state. Validated here: Gemini can't hand the
    backend an impossible weekday or time."""

    category: Literal["one_time", "recurring"] | None = None
    due_time: time | None = None
    day_selection: DaySelection | None = None
    weekdays: list[int] = []          # ISO: 1=Monday ... 7=Sunday (custom_weekdays only)
    start_date: date | None = None
    end_date: date | None = None
    times: list[time] = Field(default=[], max_length=10)  # reminder times of day

    @field_validator("weekdays", "times", mode="before")
    @classmethod
    def _null_is_empty(cls, value):
        # Gemini writes null (not []) for "none" — seen live; same meaning.
        return [] if value is None else value

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in value):
            raise ValueError("weekdays must be 1-7 (1=Monday)")
        return sorted(set(value))

    @field_validator("times")
    @classmethod
    def _times(cls, value: list[time]) -> list[time]:
        return sorted({t.replace(second=0, microsecond=0, tzinfo=None) for t in value})


class GeminiIntentOutput(_ScheduleFields):
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

    @field_validator("missing_fields", mode="before")
    @classmethod
    def _null_is_no_missing(cls, value):
        return [] if value is None else value


class ConversationState(str, enum.Enum):
    IDLE = "idle"
    COLLECTING_INFORMATION = "collecting_information"
    AWAITING_TASK_SELECTION = "awaiting_task_selection"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class PendingAction(_ScheduleFields):
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
    message: str = Field(min_length=1, max_length=1000)
    # How the user produced the message. Voice text comes from the phone's
    # speech-to-text; both go through exactly the same logic.
    input: Literal["text", "voice"] = "text"


class AssistantMessageResponse(BaseModel):
    reply: str
    state: ConversationState
