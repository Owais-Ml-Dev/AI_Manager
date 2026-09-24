from datetime import datetime

ALLOWED_PRIORITIES = {
    "important_urgent",
    "important_not_urgent",
    "not_important_urgent",
    "not_important_not_urgent"
}

ALLOWED_REPEAT_TYPES = {
    "everyday",
    "weekdays",
    "weekends",
    "custom_dates"
}

UPDATABLE_FIELDS = {
    "title",
    "description",
    "priority",
    "duration",
    "repeat",
    "reminders"
}

def parse_date(date_string):
    if not isinstance(date_string, str):
        return None
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        return None

def validate_duration(duration, errors):
    if not isinstance(duration, dict):
        errors["duration"] = "Duration must be an object."
        return

    start_date = parse_date(duration.get("start_date"))
    end_date = parse_date(duration.get("end_date"))

    if start_date is None:
        errors["duration.start_date"] = (
            "start_date must be a valid date using YYYY-MM-DD format."
        )

    if end_date is None:
        errors["duration.end_date"] = (
            "end_date must be a valid date using YYYY-MM-DD format."
        )

    if start_date is not None and end_date is not None and end_date < start_date:
        errors["duration"] = "end_date cannot be before start_date."

def validate_repeat(repeat, duration, errors):
    if not isinstance(repeat, dict):
        errors["repeat"] = "Repeat must be an object."
        return

    repeat_type = repeat.get("type")
    if repeat_type not in ALLOWED_REPEAT_TYPES:
        errors["repeat.type"] = (
            "Repeat type must be everyday, weekdays, weekends, or custom_dates."
        )
        return

    custom_dates = repeat.get("custom_dates", [])

    if not isinstance(custom_dates, list):
        errors["repeat.custom_dates"] = "custom_dates must be a list."
        return

    if repeat_type == "custom_dates":
        if not custom_dates:
            errors["repeat.custom_dates"] = "Select at least one custom date."
            return

        parsed_dates = []
        for date_string in custom_dates:
            parsed_date = parse_date(date_string)
            if parsed_date is None:
                errors["repeat.custom_dates"] = (
                    "Every custom date must be a valid YYYY-MM-DD date."
                )
                return
            parsed_dates.append(parsed_date)

        if len(custom_dates) != len(set(custom_dates)):
            errors["repeat.custom_dates"] = "Duplicate custom dates are not allowed."
            return

        if isinstance(duration, dict):
            start_date = parse_date(duration.get("start_date"))
            end_date = parse_date(duration.get("end_date"))
            if start_date is not None and end_date is not None:
                if any(d < start_date or d > end_date for d in parsed_dates):
                    errors["repeat.custom_dates"] = (
                        "Custom dates must fall inside the task duration."
                    )
    else:
        if custom_dates:
            errors["repeat.custom_dates"] = (
                "custom_dates must be empty unless repeat type is custom_dates."
            )

def validate_reminders(reminders, errors):
    if not isinstance(reminders, list):
        errors["reminders"] = "Reminders must be a list."
        return

    for index, reminder in enumerate(reminders):
        if not isinstance(reminder, dict):
            errors[f"reminders[{index}]"] = "Reminder must be an object."
            continue

        start_time = reminder.get("start_time")
        end_time = reminder.get("end_time")
        count = reminder.get("count")

        try:
            start = datetime.strptime(start_time, "%H:%M")
            end = datetime.strptime(end_time, "%H:%M")
            if start >= end:
                errors[f"reminders[{index}].time"] = (
                    "start_time must be before end_time."
                )
        except (ValueError, TypeError):
            errors[f"reminders[{index}].time"] = (
                "start_time and end_time must use HH:MM format."
            )

        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors[f"reminders[{index}].count"] = (
                "Reminder count must be an integer greater than 0."
            )

def validate_create_repeat_until_done_task(data):
    errors = {}

    if not isinstance(data, dict):
        errors["request"] = "Request body must be an object."
        return errors

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors["title"] = "Title is required."

    if "description" in data and not isinstance(data["description"], str):
        errors["description"] = "Description must be a string."

    if data.get("priority") not in ALLOWED_PRIORITIES:
        errors["priority"] = "Invalid priority."

    duration = data.get("duration")
    if duration is None:
        errors["duration"] = "Duration is required."
    else:
        validate_duration(duration, errors)

    repeat = data.get("repeat")
    if repeat is None:
        errors["repeat"] = "Repeat configuration is required."
    else:
        validate_repeat(repeat, duration, errors)

    validate_reminders(data.get("reminders", []), errors)
    return errors

def validate_update_repeat_until_done_task(data, current_task=None):
    errors = {}

    if not isinstance(data, dict) or not data:
        errors["request"] = "At least one field is required."
        return errors

    invalid_fields = set(data.keys()) - UPDATABLE_FIELDS
    if invalid_fields:
        errors["fields"] = (
            "Fields cannot be updated: " + ", ".join(sorted(invalid_fields))
        )

    if "title" in data:
        if not isinstance(data["title"], str) or not data["title"].strip():
            errors["title"] = "Title cannot be empty."

    if "description" in data and not isinstance(data["description"], str):
        errors["description"] = "Description must be a string."

    if "priority" in data and data["priority"] not in ALLOWED_PRIORITIES:
        errors["priority"] = "Invalid priority."

    existing_duration = current_task.get("duration") if current_task else None
    existing_repeat = current_task.get("repeat") if current_task else None

    effective_duration = data.get("duration", existing_duration)
    effective_repeat = data.get("repeat", existing_repeat)

    if "duration" in data:
        validate_duration(data["duration"], errors)

    if "repeat" in data:
        validate_repeat(data["repeat"], effective_duration, errors)
    elif "duration" in data and effective_repeat is not None:
        validate_repeat(effective_repeat, effective_duration, errors)

    if "reminders" in data:
        validate_reminders(data["reminders"], errors)

    return errors
