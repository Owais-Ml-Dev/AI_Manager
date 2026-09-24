from datetime import datetime, timedelta


# =========================================================
# GENERATE REMINDER TIMES
# =========================================================

def generate_reminder_times(
    start_time,
    end_time,
    count
):
    """
    Generate evenly spaced reminder times inside a window.

    Example:

        start_time = "13:00"
        end_time   = "14:00"
        count      = 3

    Result:

        [
            "13:00",
            "13:30",
            "14:00"
        ]

    If count == 1:
        the reminder is placed at start_time.
    """

    # Convert HH:MM strings into datetime objects.
    start = datetime.strptime(
        start_time,
        "%H:%M"
    )

    end = datetime.strptime(
        end_time,
        "%H:%M"
    )

    # Safety check.
    if count < 1:
        raise ValueError(
            "Reminder count must be at least 1."
        )

    # Start must be earlier than end.
    if start >= end:
        raise ValueError(
            "Start time must be before end time."
        )

    # If only one reminder is required,
    # use the beginning of the reminder window.
    if count == 1:
        return [
            start.strftime("%H:%M")
        ]

    # Calculate the full duration of the window.
    total_seconds = (
        end - start
    ).total_seconds()

    # Example:
    #
    # 13:00 -> 14:00 = 3600 seconds
    # count = 3
    #
    # There are 2 spaces between 3 reminders.
    interval_seconds = (
        total_seconds
        / (count - 1)
    )

    generated_times = []

    # Build each reminder time.
    for index in range(count):

        offset_seconds = round(
            interval_seconds * index
        )

        reminder_time = (
            start
            + timedelta(
                seconds=offset_seconds
            )
        )

        # Keep the existing HH:MM format when
        # the reminder lands exactly on a minute.
        #
        # Use HH:MM:SS only when seconds are
        # actually required.
        if reminder_time.second == 0:
            formatted_time = (
                reminder_time.strftime(
                    "%H:%M"
                )
            )
        else:
            formatted_time = (
                reminder_time.strftime(
                    "%H:%M:%S"
                )
            )

        generated_times.append(
            formatted_time
        )

    return generated_times


# =========================================================
# PREPARE REMINDER WINDOWS
# =========================================================

def prepare_reminders(reminders):
    """
    Add generated_times to every reminder window.

    Input:

    [
        {
            "start_time": "13:00",
            "end_time": "14:00",
            "count": 3
        }
    ]

    Output:

    [
        {
            "start_time": "13:00",
            "end_time": "14:00",
            "count": 3,
            "generated_times": [
                "13:00",
                "13:30",
                "14:00"
            ]
        }
    ]
    """

    prepared_reminders = []

    for reminder in reminders:

        # Calculate actual reminder times.
        generated_times = (
            generate_reminder_times(
                reminder["start_time"],
                reminder["end_time"],
                reminder["count"]
            )
        )

        # Keep both the original window and
        # the generated reminder times.
        prepared_reminders.append({
            "start_time":
                reminder["start_time"],

            "end_time":
                reminder["end_time"],

            "count":
                reminder["count"],

            "generated_times":
                generated_times
        })

    return prepared_reminders
