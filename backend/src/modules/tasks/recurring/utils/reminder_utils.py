from datetime import datetime, timedelta

def generate_reminder_times(start_time, end_time, count):
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")

    if count < 1:
        raise ValueError("Reminder count must be at least 1.")

    if start >= end:
        raise ValueError("Start time must be before end time.")

    if count == 1:
        return [start.strftime("%H:%M")]

    total_seconds = (end - start).total_seconds()
    interval_seconds = total_seconds / (count - 1)

    generated_times = []

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

        if reminder_time.second == 0:
            formatted_time = reminder_time.strftime(
                "%H:%M"
            )
        else:
            formatted_time = reminder_time.strftime(
                "%H:%M:%S"
            )

        generated_times.append(
            formatted_time
        )

    return generated_times

def prepare_reminders(reminders):
    prepared_reminders = []

    for reminder in reminders:
        generated_times = generate_reminder_times(
            reminder["start_time"],
            reminder["end_time"],
            reminder["count"]
        )

        prepared_reminders.append({
            "start_time": reminder["start_time"],
            "end_time": reminder["end_time"],
            "count": reminder["count"],
            "generated_times": generated_times
        })

    return prepared_reminders
