from bson import ObjectId
from pymongo import ReturnDocument

from src.config.db import get_db


# =========================================================
# CREATE
# =========================================================

def insert_repeat_until_done_task(task):
    """
    Insert a prepared Repeat Until Done task into MongoDB.

    Returns:
        MongoDB ObjectId of the inserted document.
    """

    # Get the active database connection.
    db = get_db()

    # Insert into the shared tasks collection.
    result = db.tasks.insert_one(task)

    # Return MongoDB-generated ID.
    return result.inserted_id


# =========================================================
# GET ACTIVE TASKS
# =========================================================

def find_all_repeat_until_done_tasks():
    """
    Return all active Repeat Until Done tasks.

    Active means:
        task_type = repeat_until_done
        status = pending

    Completed tasks do not appear here.
    """

    db = get_db()

    return list(
        db.tasks.find({
            "task_type":
                "repeat_until_done",

            "status":
                "pending"
        }).sort(
            "created_at",
            -1
        )
    )


# =========================================================
# GET HISTORY
# =========================================================

def find_completed_repeat_until_done_tasks():
    """
    Return completed Repeat Until Done tasks.

    These documents are used for the History view.

    Newest completed tasks appear first.
    """

    db = get_db()

    return list(
        db.tasks.find({
            "task_type":
                "repeat_until_done",

            "status":
                "completed"
        }).sort(
            "completed_at",
            -1
        )
    )


# =========================================================
# GET ONE TASK
# =========================================================

def find_repeat_until_done_task_by_id(
    task_id
):
    """
    Find one Repeat Until Done task by MongoDB ObjectId.

    Can return either:
        pending task
        completed task
    """

    db = get_db()

    return db.tasks.find_one({
        "_id":
            ObjectId(task_id),

        "task_type":
            "repeat_until_done"
    })


# =========================================================
# UPDATE ACTIVE TASK
# =========================================================

def update_repeat_until_done_task_by_id(
    task_id,
    update_data
):
    """
    Update only a pending Repeat Until Done task.

    Completed tasks are intentionally excluded
    from this MongoDB query.
    """

    db = get_db()

    return db.tasks.find_one_and_update(
        {
            "_id":
                ObjectId(task_id),

            "task_type":
                "repeat_until_done",

            "status":
                "pending"
        },

        {
            "$set":
                update_data
        },

        # Return the document after MongoDB updates it.
        return_document=(
            ReturnDocument.AFTER
        )
    )


# =========================================================
# COMPLETE TASK
# =========================================================

def complete_repeat_until_done_task_by_id(
    task_id,
    completed_at
):
    """
    Complete a pending Repeat Until Done task.

    Completion changes:
        status -> completed
        completed_at -> current timestamp
        updated_at -> current timestamp
        reminders_cancelled -> True

    The status=pending condition prevents the
    same task from being completed multiple times.
    """

    db = get_db()

    return db.tasks.find_one_and_update(
        {
            "_id":
                ObjectId(task_id),

            "task_type":
                "repeat_until_done",

            "status":
                "pending"
        },

        {
            "$set": {
                "status":
                    "completed",

                "completed_at":
                    completed_at,

                "updated_at":
                    completed_at,

                "reminders_cancelled":
                    True
            }
        },

        return_document=(
            ReturnDocument.AFTER
        )
    )


# =========================================================
# DELETE
# =========================================================

def delete_repeat_until_done_task_by_id(
    task_id
):
    """
    Permanently delete a Repeat Until Done task.

    Returns:
        1 when a task is deleted.
        0 when no matching task exists.
    """

    db = get_db()

    result = db.tasks.delete_one({
        "_id":
            ObjectId(task_id),

        "task_type":
            "repeat_until_done"
    })

    return result.deleted_count
