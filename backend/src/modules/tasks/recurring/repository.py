from bson import ObjectId
from pymongo import ReturnDocument

from src.config.db import get_db


# =========================================================
# RECURRING TASK: CREATE
# =========================================================

def insert_recurring_task(task):
    """
    Insert the parent recurring task into MongoDB.

    Returns:
        MongoDB ObjectId of the created task.
    """

    db = get_db()

    result = db.tasks.insert_one(task)

    return result.inserted_id


# =========================================================
# RECURRING TASK: GET ALL ACTIVE
# =========================================================

def find_all_recurring_tasks():
    """
    Return recurring tasks that currently have:

        task_type = recurring
        status = active
    """

    db = get_db()

    return list(
        db.tasks.find({
            "task_type": "recurring",
            "status": "active"
        }).sort(
            "created_at",
            -1
        )
    )


# =========================================================
# RECURRING TASK: GET HISTORY
# =========================================================

def find_ended_recurring_tasks():
    """
    Return recurring parent tasks whose lifecycle has ended.

    History is not stored in a separate collection. Ended
    recurring tasks remain in the tasks collection and are
    filtered by:

        task_type = recurring
        status = ended
    """

    db = get_db()

    return list(
        db.tasks.find({
            "task_type": "recurring",
            "status": "ended"
        }).sort(
            "ended_at",
            -1
        )
    )


# =========================================================
# RECURRING TASK: GET ONE
# =========================================================

def find_recurring_task_by_id(task_id):
    """
    Find one recurring parent task.

    Can return:
        active task
        ended task
    """

    db = get_db()

    return db.tasks.find_one({
        "_id": ObjectId(task_id),
        "task_type": "recurring"
    })


# =========================================================
# RECURRING TASK: UPDATE
# =========================================================

def update_recurring_task_by_id(
    task_id,
    update_data
):
    """
    Update an active recurring parent task.

    Ended recurring tasks cannot be edited.
    """

    db = get_db()

    return db.tasks.find_one_and_update(
        {
            "_id": ObjectId(task_id),
            "task_type": "recurring",
            "status": "active"
        },
        {
            "$set": update_data
        },
        return_document=ReturnDocument.AFTER
    )


# =========================================================
# RECURRING TASK: END
# =========================================================

def end_recurring_task_by_id(
    task_id,
    ended_at
):
    """
    Mark an active recurring parent task as ended.

    This happens after its duration has completely passed.

    Example:

        duration.end_date = 2026-09-30
        today             = 2026-10-01

        status:
            active -> ended
    """

    db = get_db()

    return db.tasks.find_one_and_update(
        {
            "_id": ObjectId(task_id),
            "task_type": "recurring",
            "status": "active"
        },
        {
            "$set": {
                "status": "ended",
                "ended_at": ended_at,
                "updated_at": ended_at
            }
        },
        return_document=ReturnDocument.AFTER
    )


# =========================================================
# RECURRING TASK: DELETE
# =========================================================

def delete_recurring_task_by_id(task_id):
    """
    Permanently delete the recurring parent task.

    Occurrences are deleted separately by
    the service layer.
    """

    db = get_db()

    result = db.tasks.delete_one({
        "_id": ObjectId(task_id),
        "task_type": "recurring"
    })

    return result.deleted_count


# =========================================================
# OCCURRENCES: CREATE MANY
# =========================================================

def insert_recurring_occurrences(
    occurrences
):
    """
    Insert generated recurring occurrences.

    Each occurrence represents one scheduled date.
    """

    if not occurrences:
        return []

    db = get_db()

    result = db.task_occurrences.insert_many(
        occurrences
    )

    return result.inserted_ids


# =========================================================
# OCCURRENCES: GET ALL FOR TASK
# =========================================================

def find_occurrences_by_task_id(
    task_id
):
    """
    Return all occurrences for one recurring task.

    Results are sorted by scheduled date.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "task_id": ObjectId(task_id)
        }).sort(
            "scheduled_date",
            1
        )
    )


# =========================================================
# OCCURRENCES: GET ONE
# =========================================================

def find_occurrence_by_id(
    occurrence_id
):
    """
    Find one recurring occurrence.
    """

    db = get_db()

    return db.task_occurrences.find_one({
        "_id": ObjectId(occurrence_id)
    })


# =========================================================
# OCCURRENCES: COMPLETE ONE
# =========================================================

def complete_occurrence_by_id(
    occurrence_id,
    completed_at
):
    """
    Complete one pending recurring occurrence.

    This affects only one scheduled date.

    It does NOT complete the recurring parent task.
    """

    db = get_db()

    return db.task_occurrences.find_one_and_update(
        {
            "_id": ObjectId(occurrence_id),
            "status": "pending"
        },
        {
            "$set": {
                "status": "completed",
                "completed_at": completed_at,
                "updated_at": completed_at,

                # Future reminders for this occurrence
                # should no longer run.
                "reminders_cancelled": True
            }
        },
        return_document=ReturnDocument.AFTER
    )


# =========================================================
# OCCURRENCES: MARK ONE MISSED
# =========================================================

def mark_occurrence_missed_by_id(
    occurrence_id,
    updated_at
):
    """
    Mark one pending occurrence as missed.
    """

    db = get_db()

    return db.task_occurrences.find_one_and_update(
        {
            "_id": ObjectId(occurrence_id),
            "status": "pending"
        },
        {
            "$set": {
                "status": "missed",
                "updated_at": updated_at,
                "reminders_cancelled": True
            }
        },
        return_document=ReturnDocument.AFTER
    )


# =========================================================
# OCCURRENCES: MARK OLD PENDING DATES MISSED
# =========================================================

def mark_past_pending_occurrences_missed(
    task_id,
    today_date,
    updated_at
):
    """
    Automatically mark old pending occurrences as missed.

    Because scheduled_date uses YYYY-MM-DD strings,
    MongoDB can safely compare them chronologically.

    Example:

        today_date = "2026-09-20"

        Sep 17 pending -> missed
        Sep 18 pending -> missed
        Sep 20 pending -> stays pending
        Sep 21 pending -> stays pending

    Today's occurrence is NOT considered missed yet.
    """

    db = get_db()

    result = db.task_occurrences.update_many(
        {
            "task_id": ObjectId(task_id),

            "status": "pending",

            "scheduled_date": {
                "$lt": today_date
            }
        },
        {
            "$set": {
                "status": "missed",
                "updated_at": updated_at,
                "reminders_cancelled": True
            }
        }
    )

    return result.modified_count


# =========================================================
# OCCURRENCES: DELETE ALL
# =========================================================

def delete_occurrences_by_task_id(
    task_id
):
    """
    Delete every occurrence belonging to one task.
    """

    db = get_db()

    result = db.task_occurrences.delete_many({
        "task_id": ObjectId(task_id)
    })

    return result.deleted_count


# =========================================================
# OCCURRENCES: DELETE ONLY PENDING
# =========================================================

def delete_pending_occurrences_by_task_id(
    task_id
):
    """
    Delete pending occurrences only.

    Completed and missed history is preserved.

    Used when the recurring schedule is edited.
    """

    db = get_db()

    result = db.task_occurrences.delete_many({
        "task_id": ObjectId(task_id),
        "status": "pending"
    })

    return result.deleted_count


# =========================================================
# OCCURRENCES: FIND PROCESSED DATES
# =========================================================

def find_processed_occurrence_dates(
    task_id
):
    """
    Return dates that already have completed or
    missed occurrence records.

    These dates should not be recreated when
    the recurring schedule changes.
    """

    db = get_db()

    occurrences = db.task_occurrences.find(
        {
            "task_id": ObjectId(task_id),

            "status": {
                "$in": [
                    "completed",
                    "missed"
                ]
            }
        },
        {
            "scheduled_date": 1
        }
    )

    return [
        occurrence["scheduled_date"]
        for occurrence in occurrences
    ]


# =========================================================
# OCCURRENCES: UPDATE PENDING REMINDERS
# =========================================================

def update_pending_occurrence_reminders(
    task_id,
    reminders,
    updated_at
):
    """
    Update reminders on currently pending occurrences.

    Completed and missed occurrences are not changed.
    """

    db = get_db()

    result = db.task_occurrences.update_many(
        {
            "task_id": ObjectId(task_id),
            "status": "pending"
        },
        {
            "$set": {
                "reminders": reminders,
                "reminders_cancelled": False,
                "updated_at": updated_at
            }
        }
    )

    return result.modified_count


# =========================================================
# OCCURRENCES: GET EVERY TASK'S OCCURRENCES FOR ONE DATE
# =========================================================

def find_occurrences_on_date(
    scheduled_date
):
    """
    Return every occurrence scheduled on one date, across ALL tasks.

    One indexed query over scheduled_date replaces per-task queries.

    Args:
        scheduled_date: "YYYY-MM-DD" string.

    Returns:
        List of raw occurrence documents.
    """

    db = get_db()

    return list(
        db.task_occurrences.find({
            "scheduled_date": scheduled_date
        })
    )

