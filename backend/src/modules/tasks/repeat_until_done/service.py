from datetime import datetime, timezone

from src.modules.tasks.repeat_until_done.repository import (
    insert_repeat_until_done_task,
    find_all_repeat_until_done_tasks,
    find_completed_repeat_until_done_tasks,
    find_repeat_until_done_task_by_id,
    update_repeat_until_done_task_by_id,
    complete_repeat_until_done_task_by_id,
    delete_repeat_until_done_task_by_id
)

from src.modules.tasks.repeat_until_done.utils.reminder_utils import (
    prepare_reminders
)


# =========================================================
# SERIALIZER
# =========================================================

def serialize_repeat_until_done_task(task):
    """
    Convert a MongoDB task document into JSON-safe data.

    ObjectId:
        converted to string.

    Datetime:
        converted to ISO-8601 string.

    This is the structure returned to Flutter / API clients.
    """

    return {
        # MongoDB document ID.
        "id":
            str(task["_id"]),

        # Feature identifier.
        "task_type":
            task["task_type"],

        # User task information.
        "title":
            task["title"],

        "description":
            task.get(
                "description",
                ""
            ),

        "priority":
            task["priority"],

        "duration":
            task.get("duration"),

        # Repeat configuration.
        #
        # New model:
        #
        # {
        #     "type": "custom_dates",
        #     "custom_dates": [
        #         "2026-09-20"
        #     ]
        # }
        "repeat":
            task.get(
                "repeat",
                {
                    "type":
                        "everyday",

                    "custom_dates":
                        []
                }
            ),

        # Reminder windows including generated_times.
        "reminders":
            task.get(
                "reminders",
                []
            ),

        # pending / completed
        "status":
            task["status"],

        # This represents whether future reminders
        # should be treated as cancelled.
        "reminders_cancelled":
            task.get(
                "reminders_cancelled",
                False
            ),

        # MongoDB datetime -> JSON string.
        "created_at": (
            task["created_at"].isoformat()
            if task.get("created_at")
            else None
        ),

        "updated_at": (
            task["updated_at"].isoformat()
            if task.get("updated_at")
            else None
        ),

        "completed_at": (
            task["completed_at"].isoformat()
            if task.get("completed_at")
            else None
        )
    }


# =========================================================
# CREATE
# =========================================================

def create_repeat_until_done_task(data):
    """
    Create a new Repeat Until Done task.

    Backend controls:
        task_type
        status
        reminders_cancelled
        created_at
        updated_at

    Frontend controls:
        title
        description
        priority
        repeat
        reminders
    """

    # Backend timestamps are stored in UTC.
    now = datetime.now(
        timezone.utc
    )

    # Convert reminder windows into reminder windows
    # containing generated reminder times.
    prepared_reminders = (
        prepare_reminders(
            data.get(
                "reminders",
                []
            )
        )
    )

    # -----------------------------------------------------
    # BUILD MONGODB DOCUMENT
    # -----------------------------------------------------

    task = {
        "task_type":
            "repeat_until_done",

        "title":
            data["title"].strip(),

        "description":
            data.get(
                "description",
                ""
            ).strip(),

        "priority":
            data["priority"],

        "duration": {
            "start_date": data["duration"]["start_date"],
            "end_date": data["duration"]["end_date"],
        },

        # Store repeat configuration.
        #
        # Examples:
        #
        # everyday:
        #
        # {
        #     "type": "everyday",
        #     "custom_dates": []
        # }
        #
        # custom dates:
        #
        # {
        #     "type": "custom_dates",
        #     "custom_dates": [
        #         "2026-09-20",
        #         "2026-09-25"
        #     ]
        # }
        "repeat": {
            "type":
                data["repeat"]["type"],

            "custom_dates":
                data["repeat"].get(
                    "custom_dates",
                    []
                )
        },

        # Reminder windows with generated times.
        "reminders":
            prepared_reminders,

        # Every new task begins pending.
        "status":
            "pending",

        # False means future reminders are still active.
        "reminders_cancelled":
            False,

        "created_at":
            now,

        "updated_at":
            now
    }

    # Insert task into MongoDB.
    task_id = (
        insert_repeat_until_done_task(
            task
        )
    )

    # MongoDB generates _id during insertion.
    # Add it to our in-memory object before serialization.
    task["_id"] = task_id

    return (
        serialize_repeat_until_done_task(
            task
        )
    )


# =========================================================
# GET ACTIVE TASKS
# =========================================================

def get_all_repeat_until_done_tasks():
    """
    Return all pending Repeat Until Done tasks.

    Completed tasks are excluded because they
    appear in History.
    """

    tasks = (
        find_all_repeat_until_done_tasks()
    )

    return [
        serialize_repeat_until_done_task(
            task
        )
        for task in tasks
    ]


# =========================================================
# GET HISTORY
# =========================================================

def get_repeat_until_done_task_history():
    """
    Return all completed Repeat Until Done tasks.
    """

    tasks = (
        find_completed_repeat_until_done_tasks()
    )

    return [
        serialize_repeat_until_done_task(
            task
        )
        for task in tasks
    ]


# =========================================================
# GET ONE TASK
# =========================================================

def get_repeat_until_done_task(task_id):
    """
    Find one Repeat Until Done task.

    Both pending and completed tasks can
    be retrieved by ID.
    """

    task = (
        find_repeat_until_done_task_by_id(
            task_id
        )
    )

    if task is None:
        return None

    return (
        serialize_repeat_until_done_task(
            task
        )
    )


# =========================================================
# UPDATE TASK
# =========================================================

def update_repeat_until_done_task(
    task_id,
    data
):
    """
    Update a pending Repeat Until Done task.

    Completed tasks cannot be modified.

    Possible return values:

        "not_found"
        "completed"
        serialized updated task
    """

    # -----------------------------------------------------
    # FIND CURRENT TASK
    # -----------------------------------------------------

    current_task = (
        find_repeat_until_done_task_by_id(
            task_id
        )
    )

    if current_task is None:
        return "not_found"

    # Completed tasks are immutable.
    if (
        current_task.get("status")
        == "completed"
    ):
        return "completed"

    # Only fields actually supplied in the PATCH request
    # are added to update_data.
    update_data = {}

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    if "title" in data:
        update_data["title"] = (
            data["title"].strip()
        )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    if "description" in data:
        update_data["description"] = (
            data["description"].strip()
        )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    if "priority" in data:
        update_data["priority"] = (
            data["priority"]
        )

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    if "duration" in data:
        update_data["duration"] = {
            "start_date": data["duration"]["start_date"],
            "end_date": data["duration"]["end_date"],
        }

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    if "repeat" in data:

        # Store the complete repeat configuration
        # as one object.
        update_data["repeat"] = {
            "type":
                data["repeat"]["type"],

            "custom_dates":
                data["repeat"].get(
                    "custom_dates",
                    []
                )
        }

    # -----------------------------------------------------
    # REMINDERS
    # -----------------------------------------------------

    if "reminders" in data:

        # Recalculate generated reminder times whenever
        # reminder windows are changed.
        update_data["reminders"] = (
            prepare_reminders(
                data["reminders"]
            )
        )

        # Since the task is still active,
        # updated reminders should not be marked cancelled.
        update_data[
            "reminders_cancelled"
        ] = False

    # Every successful edit refreshes updated_at.
    update_data["updated_at"] = (
        datetime.now(
            timezone.utc
        )
    )

    # -----------------------------------------------------
    # SAVE UPDATE
    # -----------------------------------------------------

    task = (
        update_repeat_until_done_task_by_id(
            task_id,
            update_data
        )
    )

    # Repository updates only pending tasks.
    #
    # If it returned None after we previously found
    # the task, another request may have completed
    # it at the same time.
    if task is None:
        return "completed"

    return (
        serialize_repeat_until_done_task(
            task
        )
    )


# =========================================================
# COMPLETE TASK
# =========================================================

def complete_repeat_until_done_task(
    task_id
):
    """
    Permanently complete a Repeat Until Done task.

    Once completed:

        status = completed

        completed_at = current UTC time

        reminders_cancelled = True

    It then disappears from the active-task query
    and appears in History.
    """

    # Find current task first so we can return
    # meaningful response states.
    current_task = (
        find_repeat_until_done_task_by_id(
            task_id
        )
    )

    if current_task is None:
        return "not_found"

    # Do not allow completion twice.
    if (
        current_task.get("status")
        == "completed"
    ):
        return "already_completed"

    completed_at = datetime.now(
        timezone.utc
    )

    # Repository performs the actual atomic update.
    task = (
        complete_repeat_until_done_task_by_id(
            task_id,
            completed_at
        )
    )

    # Safety check in case another request completed
    # this task at almost exactly the same moment.
    if task is None:
        return "already_completed"

    return (
        serialize_repeat_until_done_task(
            task
        )
    )


# =========================================================
# DELETE TASK
# =========================================================

def delete_repeat_until_done_task(
    task_id
):
    """
    Permanently delete a Repeat Until Done task.

    Returns:
        True  -> deleted
        False -> task not found
    """

    deleted_count = (
        delete_repeat_until_done_task_by_id(
            task_id
        )
    )

    return deleted_count == 1

