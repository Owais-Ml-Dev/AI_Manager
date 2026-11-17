"""Validation for occurrences. Users can only move a PENDING occurrence to
COMPLETED or SKIPPED — MISSED/PENDING are system-managed, not user-settable."""
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.features.occurrences.models import OccurrenceStatus


class UserSettableOccurrenceStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"


class OccurrenceUpdate(BaseModel):
    status: UserSettableOccurrenceStatus


class OccurrenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    occurrence_date: date
    status: OccurrenceStatus
    completed_at: datetime | None
