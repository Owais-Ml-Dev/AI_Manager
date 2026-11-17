"""Read-only — history events are never created/edited directly via the API,
only recorded as a side effect of other features' writes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.features.history.models import HistoryEventType


class TaskHistoryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    event_type: HistoryEventType
    field_name: str | None
    old_value: str | None
    new_value: str | None
    occurred_at: datetime
