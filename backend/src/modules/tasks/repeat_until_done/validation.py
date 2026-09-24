from datetime import datetime


# =========================================================
# ALLOWED VALUES
# =========================================================

# These are the four Eisenhower Matrix priority values
# supported by the application.
ALLOWED_PRIORITIES = {
    "important_urgent",
    "important_not_urgent",
    "not_important_urgent",
    "not_important_not_urgent"
}


# Repeat Until Done supports four repeat modes.
#
# everyday:
#     Reminders can occur every day until completion.
#
# weekdays:
#     Reminders can occur Monday-Friday until completion.
#
# weekends:
#     Reminders can occur Saturday-Sunday until completion.
#
# custom_dates:
#     Reminders can occur only on specific calendar dates.
ALLOWED_REPEAT_TYPES = {
    "everyday",
    "weekdays",
    "weekends",
    "custom_dates"
}


# These are the only fields that can be changed
# through the normal PATCH update endpoint.
#
# Backend-controlled fields such as:
# task_type, status, completed_at, created_at,
# updated_at and reminders_cancelled cannot be
# directly changed by the client.
UPDATABLE_FIELDS = {
    "title",
    "description",
    "priority",
    "repeat",
    "reminders"
}


# =========================================================
# CUSTOM DATE VALIDATION
# =========================================================

def is_valid_date(date_string):
    """
    Check whether a value is a valid YYYY-MM-DD date.

    Examples:

        2026-09-20 -> valid
        2026-02-30 -> invalid
        20-09-2026 -> invalid
        hello      -> invalid

    Returns:
        True when valid.
        False when invalid.
    """

    if not isinstance(date_string, str):
        return False

    try:
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )

        return True

    except ValueError:
        return False


# =========================================================
# REPEAT VALIDATION
# =========================================================

def validate_repeat(repeat, errors):
    """
    Validate the repeat configuration.

    Example for predefined repeat:

    {
        "type": "weekdays",
        "custom_dates": []
    }


    Example for custom dates:

    {
        "type": "custom_dates",
        "custom_dates": [
            "2026-09-20",
            "2026-09-25"
        ]
    }
    """

    # Repeat must be a JSON object / Python dictionary.
    if not isinstance(repeat, dict):
        errors["repeat"] = (
            "Repeat must be an object."
        )
        return

    repeat_type = repeat.get("type")

    # Make sure the repeat type is supported.
    if repeat_type not in ALLOWED_REPEAT_TYPES:
        errors["repeat.type"] = (
            "Repeat type must be everyday, "
            "weekdays, weekends, or custom_dates."
        )
        return

    # custom_dates defaults to an empty list.
    custom_dates = repeat.get(
        "custom_dates",
        []
    )

    # custom_dates must always be represented as a list.
    if not isinstance(custom_dates, list):
        errors["repeat.custom_dates"] = (
            "custom_dates must be a list."
        )
        return

    # -----------------------------------------------------
    # CUSTOM DATES
    # -----------------------------------------------------

    if repeat_type == "custom_dates":

        # At least one calendar date must be selected.
        if len(custom_dates) == 0:
            errors["repeat.custom_dates"] = (
                "Select at least one date "
                "for custom_dates repeat."
            )
            return

        # Find dates that either:
        # - are not strings
        # - do not use YYYY-MM-DD
        # - are impossible calendar dates
        invalid_dates = [
            date
            for date in custom_dates
            if not is_valid_date(date)
        ]

        if invalid_dates:
            errors["repeat.custom_dates"] = (
                "All custom dates must be valid "
                "calendar dates using YYYY-MM-DD format."
            )
            return

        # Prevent duplicate dates such as:
        #
        # [
        #     "2026-09-20",
        #     "2026-09-20"
        # ]
        if len(custom_dates) != len(
            set(custom_dates)
        ):
            errors["repeat.custom_dates"] = (
                "Duplicate custom dates are not allowed."
            )

    # -----------------------------------------------------
    # EVERYDAY / WEEKDAYS / WEEKENDS
    # -----------------------------------------------------

    else:

        # Predefined repeat patterns do not use
        # specific custom dates.
        if custom_dates:
            errors["repeat.custom_dates"] = (
                "custom_dates must be empty unless "
                "repeat type is custom_dates."
            )


# =========================================================
# REMINDER VALIDATION
# =========================================================

def validate_reminders(reminders, errors):
    """
    Validate reminder windows.

    Example:

    {
        "start_time": "13:00",
        "end_time": "14:00",
        "count": 3
    }

    Rules:
        - reminders must be a list
        - start_time must use HH:MM
        - end_time must use HH:MM
        - start_time must be before end_time
        - count must be an integer >= 1
    """

    # reminders must always be represented as a list.
    if not isinstance(reminders, list):
        errors["reminders"] = (
            "Reminders must be a list."
        )
        return

    # Validate every reminder window separately.
    for index, reminder in enumerate(
        reminders
    ):

        # Every reminder item must be an object.
        if not isinstance(reminder, dict):
            errors[
                f"reminders[{index}]"
            ] = (
                "Reminder must be an object."
            )

            continue

        start_time = reminder.get(
            "start_time"
        )

        end_time = reminder.get(
            "end_time"
        )

        count = reminder.get(
            "count"
        )

        # -------------------------------------------------
        # TIME VALIDATION
        # -------------------------------------------------

        try:
            start = datetime.strptime(
                start_time,
                "%H:%M"
            )

            end = datetime.strptime(
                end_time,
                "%H:%M"
            )

            # Reminder windows currently cannot cross
            # midnight, so start must be before end.
            if start >= end:
                errors[
                    f"reminders[{index}].time"
                ] = (
                    "start_time must be "
                    "before end_time."
                )

        except (ValueError, TypeError):

            errors[
                f"reminders[{index}].time"
            ] = (
                "start_time and end_time "
                "must use HH:MM format."
            )

        # -------------------------------------------------
        # COUNT VALIDATION
        # -------------------------------------------------

        # Python considers bool a subclass of int,
        # so explicitly reject True and False.
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 1
        ):
            errors[
                f"reminders[{index}].count"
            ] = (
                "Reminder count must be an integer "
                "greater than 0."
            )


# =========================================================
# CREATE VALIDATION
# =========================================================

def validate_create_repeat_until_done_task(
    data
):
    """
    Validate the request body used to create
    a Repeat Until Done task.

    Required:
        title
        priority
        repeat

    Optional:
        description
        reminders
    """

    errors = {}

    # Request body must be a JSON object.
    if not isinstance(data, dict):
        errors["request"] = (
            "Request body must be an object."
        )

        return errors

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    title = data.get("title")

    if (
        not isinstance(title, str)
        or not title.strip()
    ):
        errors["title"] = (
            "Title is required."
        )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    if "description" in data:

        if not isinstance(
            data["description"],
            str
        ):
            errors["description"] = (
                "Description must be a string."
            )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    priority = data.get("priority")

    if priority not in ALLOWED_PRIORITIES:
        errors["priority"] = (
            "Invalid priority."
        )

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    repeat = data.get("repeat")

    if repeat is None:
        errors["repeat"] = (
            "Repeat configuration is required."
        )

    else:
        validate_repeat(
            repeat,
            errors
        )

    # -----------------------------------------------------
    # REMINDERS
    # -----------------------------------------------------

    # No reminders is currently allowed.
    # If omitted, it becomes an empty list.
    reminders = data.get(
        "reminders",
        []
    )

    validate_reminders(
        reminders,
        errors
    )

    return errors


# =========================================================
# UPDATE VALIDATION
# =========================================================

def validate_update_repeat_until_done_task(
    data
):
    """
    Validate PATCH data for a Repeat Until Done task.

    Only these fields can be changed:

        title
        description
        priority
        repeat
        reminders

    Lifecycle fields are controlled by the backend.
    """

    errors = {}

    # PATCH must contain at least one field.
    if not isinstance(data, dict) or not data:
        errors["request"] = (
            "At least one field is required."
        )

        return errors

    # -----------------------------------------------------
    # PROTECTED FIELD CHECK
    # -----------------------------------------------------

    invalid_fields = (
        set(data.keys())
        - UPDATABLE_FIELDS
    )

    if invalid_fields:
        errors["fields"] = (
            "Fields cannot be updated: "
            + ", ".join(
                sorted(invalid_fields)
            )
        )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    if "title" in data:

        if (
            not isinstance(
                data["title"],
                str
            )
            or not data["title"].strip()
        ):
            errors["title"] = (
                "Title cannot be empty."
            )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    if "description" in data:

        if not isinstance(
            data["description"],
            str
        ):
            errors["description"] = (
                "Description must be a string."
            )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    if "priority" in data:

        if (
            data["priority"]
            not in ALLOWED_PRIORITIES
        ):
            errors["priority"] = (
                "Invalid priority."
            )

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    if "repeat" in data:
        validate_repeat(
            data["repeat"],
            errors
        )

    # -----------------------------------------------------
    # REMINDERS
    # -----------------------------------------------------

    if "reminders" in data:
        validate_reminders(
            data["reminders"],
            errors
        )

    return errors
