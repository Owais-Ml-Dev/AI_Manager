"""Request/response validation for tasks."""
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.features.tasks.models import TaskCategory, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: TaskCategory
    description: str | None = Field(default=None, max_length=2000)
    urgent: bool
    important: bool
    due_date: date | None = None
    due_time: time | None = None

    @model_validator(mode="after")
    def validate_due_date_time(self) -> "TaskCreate":
        if self.category != TaskCategory.ONE_TIME and (self.due_date or self.due_time):
            raise ValueError("due_date/due_time only apply to one-time tasks")
        if self.due_time is not None and self.due_date is None:
            raise ValueError("due_time requires due_date to be set")
        return self


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    urgent: bool | None = None
    important: bool | None = None
    status: TaskStatus | None = None
    due_date: date | None = None
    due_time: time | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: UUID
    title: str
    description: str | None
    category: TaskCategory
    urgent: bool
    important: bool
    status: TaskStatus
    due_date: date | None
    due_time: time | None
    created_at: datetime
    updated_at: datetime


class QuadrantGroup(BaseModel):
    total: int
    completed: int
    tasks: list[TaskRead]


class MatrixRead(BaseModel):
    do_first: QuadrantGroup  # urgent + important
    schedule: QuadrantGroup  # important, not urgent
    delegate: QuadrantGroup  # urgent, not important
    eliminate: QuadrantGroup  # neither
