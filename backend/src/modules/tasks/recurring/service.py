from datetime import datetime, timezone

from src.modules.tasks.recurring.repository import (
    insert_recurring_task,
    find_all_recurring_tasks,
    find_ended_recurring_tasks,
    find_recurring_task_by_id,
    update_recurring_task_by_id,
    end_recurring_task_by_id,
    delete_recurring_task_by_id,
    insert_recurring_occurrences,
    find_occurrences_by_task_id,
    find_occurrence_by_id,
    complete_occurrence_by_id,
    delete_occurrences_by_task_id,
    delete_pending_occurrences_by_task_id,
    find_processed_occurrence_dates,
    update_pending_occurrence_reminders,
    mark_past_pending_occurrences_missed
)

from src.modules.tasks.recurring.utils.occurrence_utils import (
    generate_occurrence_dates
)

from src.modules.tasks.recurring.utils.reminder_utils import (
    prepare_reminders
)


# =========================================================
# PARENT TASK SERIALIZER
# =========================================================

def serialize_recurring_task(task):
    """
    Convert MongoDB recurring parent task data
    into JSON-safe API data.
    """

    return {
        "id":
            str(task["_id"]),

        "task_type":
            task["task_type"],

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
            task["duration"],

        "repeat":
            task["repeat"],

        "reminders":
            task.get(
                "reminders",
                []
            ),

        # Parent lifecycle:
        #
        # active
        # ended
        "status":
            task["status"],

        "occurrence_count":
            task.get(
                "occurrence_count",
                0
            ),

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

        "ended_at": (
            task["ended_at"].isoformat()
            if task.get("ended_at")
            else None
        )
    }


# =========================================================
# OCCURRENCE SERIALIZER
# =========================================================

def serialize_recurring_occurrence(
    occurrence
):
    """
    Convert one recurring occurrence into
    JSON-safe API data.
    """

    return {
        "id":
            str(occurrence["_id"]),

        "task_id":
            str(occurrence["task_id"]),

        "scheduled_date":
            occurrence["scheduled_date"],

        # Occurrence lifecycle:
        #
        # pending
        # completed
        # missed
        "status":
            occurrence["status"],

        "reminders":
            occurrence.get(
                "reminders",
                []
            ),

        "reminders_cancelled":
            occurrence.get(
                "reminders_cancelled",
                False
            ),

        "created_at": (
            occurrence["created_at"].isoformat()
            if occurrence.get("created_at")
            else None
        ),

        "updated_at": (
            occurrence["updated_at"].isoformat()
            if occurrence.get("updated_at")
            else None
        ),

        "completed_at": (
            occurrence["completed_at"].isoformat()
            if occurrence.get("completed_at")
            else None
        )
    }


# =========================================================
# LIFECYCLE SYNCHRONIZATION
# =========================================================

def sync_recurring_task_lifecycle(
    task
):
    """
    Synchronize one recurring task with the current date.

    This performs two lifecycle operations:

    1. Any pending occurrence before today becomes missed.

    2. If today is after duration.end_date:
           parent status becomes ended.

    Important:
        This currently runs when recurring APIs are used.

        Later, a background scheduler can call the same
        lifecycle logic automatically without an API request.
    """

    if task is None:
        return None

    # Ended tasks no longer need lifecycle processing.
    if task.get("status") != "active":
        return task

    now = datetime.now(
        timezone.utc
    )

    # YYYY-MM-DD is used for occurrence dates.
    today_date = now.date().isoformat()

    # -----------------------------------------------------
    # MARK OLD PENDING OCCURRENCES AS MISSED
    # -----------------------------------------------------

    mark_past_pending_occurrences_missed(
        str(task["_id"]),
        today_date,
        now
    )

    # -----------------------------------------------------
    # END PARENT AFTER DURATION
    # -----------------------------------------------------

    end_date = task[
        "duration"
    ][
        "end_date"
    ]

    # String comparison is safe because both values
    # use YYYY-MM-DD.
    if today_date > end_date:

        ended_task = (
            end_recurring_task_by_id(
                str(task["_id"]),
                now
            )
        )

        if ended_task is not None:
            return ended_task

    return task


# =========================================================
# CREATE RECURRING TASK
# =========================================================

def create_recurring_task(data):
    """
    Create:
        1 parent recurring task
        1 occurrence per scheduled date
    """

    now = datetime.now(
        timezone.utc
    )

    # Generate reminder times.
    prepared_reminders = (
        prepare_reminders(
            data.get(
                "reminders",
                []
            )
        )
    )

    # Generate actual scheduled dates.
    occurrence_dates = (
        generate_occurrence_dates(
            data["duration"],
            data["repeat"]
        )
    )

    # -----------------------------------------------------
    # BUILD PARENT TASK
    # -----------------------------------------------------

    recurring_task = {
        "task_type":
            "recurring",

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
            "start_date":
                data["duration"]["start_date"],

            "end_date":
                data["duration"]["end_date"]
        },

        "repeat": {
            "type":
                data["repeat"]["type"],

            "custom_dates":
                data["repeat"].get(
                    "custom_dates",
                    []
                )
        },

        "reminders":
            prepared_reminders,

        "status":
            "active",

        "occurrence_count":
            len(occurrence_dates),

        "created_at":
            now,

        "updated_at":
            now
    }

    task_id = (
        insert_recurring_task(
            recurring_task
        )
    )

    recurring_task["_id"] = task_id

    # -----------------------------------------------------
    # BUILD OCCURRENCES
    # -----------------------------------------------------

    occurrences = []

    for scheduled_date in occurrence_dates:

        occurrences.append({
            "task_id":
                task_id,

            "scheduled_date":
                scheduled_date,

            "status":
                "pending",

            "reminders":
                prepared_reminders,

            "reminders_cancelled":
                False,

            "completed_at":
                None,

            "created_at":
                now,

            "updated_at":
                now
        })

    # -----------------------------------------------------
    # SAVE OCCURRENCES
    # -----------------------------------------------------

    try:
        inserted_ids = (
            insert_recurring_occurrences(
                occurrences
            )
        )

    except Exception:

        # Prevent parent task from remaining if
        # occurrence creation fails.
        delete_recurring_task_by_id(
            str(task_id)
        )

        raise

    for occurrence, occurrence_id in zip(
        occurrences,
        inserted_ids
    ):
        occurrence["_id"] = occurrence_id

    return {
        "task":
            serialize_recurring_task(
                recurring_task
            ),

        "occurrences": [
            serialize_recurring_occurrence(
                occurrence
            )
            for occurrence in occurrences
        ]
    }


# =========================================================
# GET ALL ACTIVE TASKS
# =========================================================

def get_all_recurring_tasks():
    """
    Return currently active recurring tasks.

    Before returning them, each task lifecycle is synced.
    """

    tasks = (
        find_all_recurring_tasks()
    )

    active_tasks = []

    for task in tasks:

        synced_task = (
            sync_recurring_task_lifecycle(
                task
            )
        )

        # If synchronization ended the task,
        # do not include it in the active list.
        if (
            synced_task.get("status")
            == "active"
        ):
            active_tasks.append(
                serialize_recurring_task(
                    synced_task
                )
            )

    return active_tasks


# =========================================================
# OCCURRENCE SUMMARY
# =========================================================

def build_recurring_occurrence_summary(occurrences):
    """
    Build the statistics used by the recurring task detail
    and recurring history screens.

    Completion rate intentionally considers only processed
    occurrences:

        completed / (completed + missed)

    Future/pending occurrences do not reduce the rate.

    Example:
        completed = 23
        missed = 5

        23 / (23 + 5) = 82%
    """

    completed_count = sum(
        1
        for occurrence in occurrences
        if occurrence.get("status") == "completed"
    )

    missed_count = sum(
        1
        for occurrence in occurrences
        if occurrence.get("status") == "missed"
    )

    pending_count = sum(
        1
        for occurrence in occurrences
        if occurrence.get("status") == "pending"
    )

    processed_count = (
        completed_count
        + missed_count
    )

    completion_rate = (
        round(
            (
                completed_count
                / processed_count
            )
            * 100
        )
        if processed_count > 0
        else 0
    )

    return {
        "done": completed_count,
        "missed": missed_count,
        "pending": pending_count,
        "processed": processed_count,
        "total": len(occurrences),
        "completion_rate": completion_rate
    }


# =========================================================
# GET RECURRING TASK HISTORY
# =========================================================

def get_recurring_task_history():
    """
    Return recurring parent tasks that have ended.

    Before reading history, synchronize active recurring
    tasks so any task whose duration has expired can move:

        active -> ended

    Each history item includes a compact occurrence summary
    for the History UI. Full calendar data is available from
    the task details endpoint.
    """

    # Catch tasks whose duration expired since the last
    # scheduler/API lifecycle synchronization.
    sync_all_recurring_tasks_lifecycle()

    tasks = find_ended_recurring_tasks()

    history = []

    for task in tasks:
        occurrences = find_occurrences_by_task_id(
            str(task["_id"])
        )

        history.append({
            "task": serialize_recurring_task(task),
            "summary": build_recurring_occurrence_summary(
                occurrences
            )
        })

    return history


# =========================================================
# GET RECURRING TASK DETAILS
# =========================================================

def get_recurring_task_details(task_id):
    """
    Return everything needed by the recurring task detail UI.

    Works for both:
        - active recurring tasks
        - ended recurring tasks

    The response contains:
        task
        summary
        today_occurrence
        occurrences

    Occurrences are retained after the parent task ends, so
    the same detail screen can be reused from History.
    """

    task = find_recurring_task_by_id(
        task_id
    )

    if task is None:
        return None

    # For an active task this marks old pending dates missed
    # and ends the parent if its duration has expired.
    task = sync_recurring_task_lifecycle(
        task
    )

    occurrences = find_occurrences_by_task_id(
        task_id
    )

    serialized_occurrences = [
        serialize_recurring_occurrence(
            occurrence
        )
        for occurrence in occurrences
    ]

    today_date = datetime.now(
        timezone.utc
    ).date().isoformat()

    today_occurrence = next(
        (
            serialized_occurrence
            for serialized_occurrence
            in serialized_occurrences
            if serialized_occurrence[
                "scheduled_date"
            ] == today_date
        ),
        None
    )

    return {
        "task": serialize_recurring_task(
            task
        ),
        "summary": build_recurring_occurrence_summary(
            occurrences
        ),
        "today_occurrence": today_occurrence,
        "occurrences": serialized_occurrences
    }


# =========================================================
# GET ONE TASK
# =========================================================

def get_recurring_task(task_id):
    """
    Return one recurring parent task.

    Lifecycle is synchronized before returning it.
    """

    task = (
        find_recurring_task_by_id(
            task_id
        )
    )

    if task is None:
        return None

    task = (
        sync_recurring_task_lifecycle(
            task
        )
    )

    return (
        serialize_recurring_task(
            task
        )
    )


# =========================================================
# GET OCCURRENCES
# =========================================================

def get_recurring_task_occurrences(
    task_id
):
    """
    Return all occurrences for one recurring task.

    Lifecycle is synchronized first so old pending
    occurrences appear as missed.
    """

    parent_task = (
        find_recurring_task_by_id(
            task_id
        )
    )

    if parent_task is not None:

        sync_recurring_task_lifecycle(
            parent_task
        )

    occurrences = (
        find_occurrences_by_task_id(
            task_id
        )
    )

    return [
        serialize_recurring_occurrence(
            occurrence
        )
        for occurrence in occurrences
    ]


# =========================================================
# GET ONE OCCURRENCE
# =========================================================

def get_recurring_occurrence(
    occurrence_id
):
    """
    Return one recurring occurrence.

    Its parent lifecycle is synchronized first.
    """

    occurrence = (
        find_occurrence_by_id(
            occurrence_id
        )
    )

    if occurrence is None:
        return None

    parent_task = (
        find_recurring_task_by_id(
            str(occurrence["task_id"])
        )
    )

    if parent_task is not None:

        sync_recurring_task_lifecycle(
            parent_task
        )

        # Read occurrence again because its status
        # may have changed from pending -> missed.
        occurrence = (
            find_occurrence_by_id(
                occurrence_id
            )
        )

    return (
        serialize_recurring_occurrence(
            occurrence
        )
    )


# =========================================================
# COMPLETE ONE OCCURRENCE
# =========================================================

def complete_recurring_occurrence(
    occurrence_id
):
    """
    Complete one occurrence only.

    Before completion, lifecycle is synchronized.

    This prevents old occurrences from being completed
    after they should already be marked missed.
    """

    current_occurrence = (
        find_occurrence_by_id(
            occurrence_id
        )
    )

    if current_occurrence is None:
        return "not_found"

    # -----------------------------------------------------
    # SYNC PARENT FIRST
    # -----------------------------------------------------

    parent_task = (
        find_recurring_task_by_id(
            str(
                current_occurrence[
                    "task_id"
                ]
            )
        )
    )

    if parent_task is not None:

        sync_recurring_task_lifecycle(
            parent_task
        )

        # Fetch again after lifecycle processing.
        current_occurrence = (
            find_occurrence_by_id(
                occurrence_id
            )
        )

    # -----------------------------------------------------
    # CHECK OCCURRENCE STATE
    # -----------------------------------------------------

    if (
        current_occurrence.get("status")
        == "completed"
    ):
        return "already_completed"

    if (
        current_occurrence.get("status")
        == "missed"
    ):
        return "missed"

    completed_at = datetime.now(
        timezone.utc
    )

    occurrence = (
        complete_occurrence_by_id(
            occurrence_id,
            completed_at
        )
    )

    if occurrence is None:
        return "already_processed"

    return (
        serialize_recurring_occurrence(
            occurrence
        )
    )



# =========================================================
# COMPLETE RECURRING TASK PERMANENTLY
# =========================================================

def complete_recurring_task(
    task_id
):
    """
    Permanently finish an active recurring task.

    Completed and missed occurrences are preserved.
    Pending occurrences are removed because they will
    never happen after the recurring series is ended.
    """

    task = find_recurring_task_by_id(
        task_id
    )

    if task is None:
        return "not_found"

    task = sync_recurring_task_lifecycle(
        task
    )

    if task.get("status") != "active":
        return "already_ended"

    completed_at = datetime.now(
        timezone.utc
    )

    ended_task = end_recurring_task_by_id(
        task_id,
        completed_at
    )

    if ended_task is None:
        return "already_ended"

    # Preserve completed/missed history but remove
    # occurrences that will never take place.
    delete_pending_occurrences_by_task_id(
        task_id
    )

    return serialize_recurring_task(
        ended_task
    )


# =========================================================
# UPDATE RECURRING TASK
# =========================================================

def update_recurring_task(
    task_id,
    data
):
    """
    Update an active recurring task.

    Completed/missed occurrence history is preserved.

    Pending occurrences are regenerated when
    duration or repeat configuration changes.
    """

    current_task = (
        find_recurring_task_by_id(
            task_id
        )
    )

    if current_task is None:
        return "not_found"

    # First ensure duration has not already expired.
    current_task = (
        sync_recurring_task_lifecycle(
            current_task
        )
    )

    if (
        current_task.get("status")
        != "active"
    ):
        return "inactive"

    now = datetime.now(
        timezone.utc
    )

    update_data = {}

    # -----------------------------------------------------
    # SIMPLE FIELDS
    # -----------------------------------------------------

    if "title" in data:
        update_data["title"] = (
            data["title"].strip()
        )

    if "description" in data:
        update_data["description"] = (
            data["description"].strip()
        )

    if "priority" in data:
        update_data["priority"] = (
            data["priority"]
        )

    # -----------------------------------------------------
    # EFFECTIVE SCHEDULE
    # -----------------------------------------------------

    effective_duration = data.get(
        "duration",
        current_task["duration"]
    )

    effective_repeat = data.get(
        "repeat",
        current_task["repeat"]
    )

    schedule_changed = (
        "duration" in data
        or "repeat" in data
    )

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    if "duration" in data:

        update_data["duration"] = {
            "start_date":
                data["duration"]["start_date"],

            "end_date":
                data["duration"]["end_date"]
        }

    # -----------------------------------------------------
    # REPEAT
    # -----------------------------------------------------

    if "repeat" in data:

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

    prepared_reminders = None

    if "reminders" in data:

        prepared_reminders = (
            prepare_reminders(
                data["reminders"]
            )
        )

        update_data["reminders"] = (
            prepared_reminders
        )

    # -----------------------------------------------------
    # REGENERATE SCHEDULE
    # -----------------------------------------------------

    if schedule_changed:

        new_occurrence_dates = (
            generate_occurrence_dates(
                effective_duration,
                effective_repeat
            )
        )

        # Completed and missed dates are history
        # and must remain untouched.
        processed_dates = set(
            find_processed_occurrence_dates(
                task_id
            )
        )

        pending_dates = [
            scheduled_date
            for scheduled_date
            in new_occurrence_dates
            if scheduled_date
            not in processed_dates
        ]

        # Delete old pending schedule.
        delete_pending_occurrences_by_task_id(
            task_id
        )

        occurrence_reminders = (
            prepared_reminders
            if prepared_reminders is not None
            else current_task.get(
                "reminders",
                []
            )
        )

        new_occurrences = []

        for scheduled_date in pending_dates:

            new_occurrences.append({
                "task_id":
                    current_task["_id"],

                "scheduled_date":
                    scheduled_date,

                "status":
                    "pending",

                "reminders":
                    occurrence_reminders,

                "reminders_cancelled":
                    False,

                "completed_at":
                    None,

                "created_at":
                    now,

                "updated_at":
                    now
            })

        insert_recurring_occurrences(
            new_occurrences
        )

        update_data[
            "occurrence_count"
        ] = len(
            new_occurrence_dates
        )

    # -----------------------------------------------------
    # REMINDER-ONLY UPDATE
    # -----------------------------------------------------

    elif prepared_reminders is not None:

        update_pending_occurrence_reminders(
            task_id,
            prepared_reminders,
            now
        )

    # -----------------------------------------------------
    # UPDATE PARENT
    # -----------------------------------------------------

    update_data["updated_at"] = now

    task = (
        update_recurring_task_by_id(
            task_id,
            update_data
        )
    )

    if task is None:
        return "inactive"

    return (
        serialize_recurring_task(
            task
        )
    )


# =========================================================
# DELETE RECURRING TASK
# =========================================================

def delete_recurring_task(task_id):
    """
    Permanently delete:
        recurring parent
        +
        all occurrences
    """

    task = (
        find_recurring_task_by_id(
            task_id
        )
    )

    if task is None:
        return False

    delete_occurrences_by_task_id(
        task_id
    )

    deleted_count = (
        delete_recurring_task_by_id(
            task_id
        )
    )

    return deleted_count == 1


# =========================================================
# SYNC ALL RECURRING TASKS
# =========================================================

def sync_all_recurring_tasks_lifecycle():
    """
    Run lifecycle synchronization for every currently
    active recurring task.

    This function is designed for the background scheduler.

    For every active recurring task it will:

        1. Mark past pending occurrences as missed.

        2. Change the parent task from:
               active
           to:
               ended

           when its duration has expired.

    Returns statistics so the scheduler can log
    what happened.
    """

    # Repository returns active recurring tasks only.
    tasks = (
        find_all_recurring_tasks()
    )

    checked_count = 0
    ended_count = 0

    for task in tasks:

        checked_count += 1

        original_status = (
            task.get("status")
        )

        synced_task = (
            sync_recurring_task_lifecycle(
                task
            )
        )

        # Count tasks that changed from active -> ended.
        if (
            original_status == "active"
            and synced_task.get("status") == "ended"
        ):
            ended_count += 1

    return {
        "checked":
            checked_count,

        "ended":
            ended_count
    }

