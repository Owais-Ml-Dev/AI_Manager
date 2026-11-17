"""Validation for reminder config and reminder times. Reminder config uses
full-replace semantics (PUT), not partial PATCH, because the day-selection
fields are cross-validated as one unit. Reminder times are individually
addable/editable/removable, so they're a separate sub-resource."""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, model_validator

from app.features.reminders.models import DaySelectionType, DeliveryStatus


class ReminderConfigWrite(BaseModel):
    start_date: date
    # Optional: no end_date means indefinite recurrence. Service layer
    # requires this to be set for one-time tasks (enforced there, since this
    # schema doesn't know the task's category).
    end_date: date | None = None
    day_selection_type: DaySelectionType
    custom_weekdays: list[int] | None = None
    custom_dates: list[date] | None = None

    @model_validator(mode="after")
    def validate_range_and_day_selection(self) -> "ReminderConfigWrite":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")

        if self.day_selection_type == DaySelectionType.CUSTOM_WEEKDAYS:
            if not self.custom_weekdays:
                raise ValueError("custom_weekdays is required when day_selection_type is custom_weekdays")
            if any(day < 1 or day > 7 for day in self.custom_weekdays):
                raise ValueError("custom_weekdays values must be 1-7 (1=Monday, 7=Sunday)")
            if self.custom_dates:
                raise ValueError("custom_dates must not be set when day_selection_type is custom_weekdays")

        elif self.day_selection_type == DaySelectionType.CUSTOM_DATES:
            if not self.custom_dates:
                raise ValueError("custom_dates is required when day_selection_type is custom_dates")
            if any(d < self.start_date for d in self.custom_dates):
                raise ValueError("all custom_dates must be on or after start_date")
            if self.end_date is not None and any(d > self.end_date for d in self.custom_dates):
                raise ValueError("all custom_dates must be on or before end_date")
            if self.custom_weekdays:
                raise ValueError("custom_weekdays must not be set when day_selection_type is custom_dates")

        else:
            if self.custom_weekdays or self.custom_dates:
                raise ValueError(
                    "custom_weekdays/custom_dates must not be set unless day_selection_type "
                    "is custom_weekdays or custom_dates"
                )

        return self


class ReminderConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    start_date: date
    end_date: date | None
    day_selection_type: DaySelectionType
    custom_weekdays: list[int] | None
    custom_dates: list[date] | None


class ReminderTimeWrite(BaseModel):
    time_of_day: time


class ReminderTimeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reminder_config_id: int
    time_of_day: time


class ReminderDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    reminder_time_id: int
    scheduled_for: datetime
    status: DeliveryStatus
    sent_at: datetime | None
