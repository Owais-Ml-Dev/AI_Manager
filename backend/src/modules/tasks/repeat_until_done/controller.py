from bson.errors import InvalidId
from flask import jsonify, request

from src.modules.tasks.repeat_until_done.service import (
    create_repeat_until_done_task,
    get_all_repeat_until_done_tasks,
    get_repeat_until_done_task_history,
    get_repeat_until_done_task,
    update_repeat_until_done_task,
    complete_repeat_until_done_task,
    delete_repeat_until_done_task
)

from src.modules.tasks.repeat_until_done.validation import (
    validate_create_repeat_until_done_task,
    validate_update_repeat_until_done_task
)


# =========================================================
# CREATE
# =========================================================

def create_repeat_until_done_task_controller():
    """
    Handle:

    POST /api/tasks/repeat-until-done
    """

    # Safely read incoming JSON.
    data = request.get_json(
        silent=True
    )

    if not data:
        return jsonify({
            "success": False,
            "message":
                "Request body is required."
        }), 400

    # Validate request before business logic runs.
    errors = (
        validate_create_repeat_until_done_task(
            data
        )
    )

    if errors:
        return jsonify({
            "success": False,
            "message":
                "Validation failed.",
            "errors":
                errors
        }), 400

    # Create the task through the service layer.
    task = (
        create_repeat_until_done_task(
            data
        )
    )

    return jsonify({
        "success":
            True,

        "message":
            "Repeat Until Done task "
            "created successfully.",

        "data":
            task
    }), 201


# =========================================================
# GET ACTIVE TASKS
# =========================================================

def get_all_repeat_until_done_tasks_controller():
    """
    Handle:

    GET /api/tasks/repeat-until-done

    Returns only pending tasks.
    """

    tasks = (
        get_all_repeat_until_done_tasks()
    )

    return jsonify({
        "success":
            True,

        "count":
            len(tasks),

        "data":
            tasks
    }), 200


# =========================================================
# GET HISTORY
# =========================================================

def get_repeat_until_done_task_history_controller():
    """
    Handle:

    GET /api/tasks/repeat-until-done/history

    Returns only completed tasks.
    """

    tasks = (
        get_repeat_until_done_task_history()
    )

    return jsonify({
        "success":
            True,

        "count":
            len(tasks),

        "data":
            tasks
    }), 200


# =========================================================
# GET ONE TASK
# =========================================================

def get_repeat_until_done_task_controller(
    task_id
):
    """
    Handle:

    GET /api/tasks/repeat-until-done/<task_id>
    """

    try:
        task = (
            get_repeat_until_done_task(
                task_id
            )
        )

    except InvalidId:
        return jsonify({
            "success":
                False,

            "message":
                "Invalid task ID."
        }), 400

    if task is None:
        return jsonify({
            "success":
                False,

            "message":
                "Repeat Until Done task "
                "not found."
        }), 404

    return jsonify({
        "success":
            True,

        "data":
            task
    }), 200


# =========================================================
# UPDATE
# =========================================================

def update_repeat_until_done_task_controller(
    task_id
):
    """
    Handle:

    PATCH /api/tasks/repeat-until-done/<task_id>
    """

    data = request.get_json(
        silent=True
    )

    if not data:
        return jsonify({
            "success":
                False,

            "message":
                "Request body is required."
        }), 400

    # Validate the partial update.
    errors = (
        validate_update_repeat_until_done_task(
            data
        )
    )

    if errors:
        return jsonify({
            "success":
                False,

            "message":
                "Validation failed.",

            "errors":
                errors
        }), 400

    try:
        result = (
            update_repeat_until_done_task(
                task_id,
                data
            )
        )

    except InvalidId:
        return jsonify({
            "success":
                False,

            "message":
                "Invalid task ID."
        }), 400

    if result == "not_found":
        return jsonify({
            "success":
                False,

            "message":
                "Repeat Until Done task "
                "not found."
        }), 404

    if result == "completed":
        return jsonify({
            "success":
                False,

            "message":
                "Completed Repeat Until Done "
                "tasks cannot be updated."
        }), 409

    return jsonify({
        "success":
            True,

        "message":
            "Repeat Until Done task "
            "updated successfully.",

        "data":
            result
    }), 200


# =========================================================
# COMPLETE
# =========================================================

def complete_repeat_until_done_task_controller(
    task_id
):
    """
    Handle:

    PATCH
    /api/tasks/repeat-until-done/<task_id>/complete

    No request body is needed.
    """

    try:
        result = (
            complete_repeat_until_done_task(
                task_id
            )
        )

    except InvalidId:
        return jsonify({
            "success":
                False,

            "message":
                "Invalid task ID."
        }), 400

    if result == "not_found":
        return jsonify({
            "success":
                False,

            "message":
                "Repeat Until Done task "
                "not found."
        }), 404

    if result == "already_completed":
        return jsonify({
            "success":
                False,

            "message":
                "Repeat Until Done task "
                "is already completed."
        }), 409

    return jsonify({
        "success":
            True,

        "message":
            "Repeat Until Done task "
            "completed successfully.",

        "data":
            result
    }), 200


# =========================================================
# DELETE
# =========================================================

def delete_repeat_until_done_task_controller(
    task_id
):
    """
    Handle:

    DELETE /api/tasks/repeat-until-done/<task_id>
    """

    try:
        deleted = (
            delete_repeat_until_done_task(
                task_id
            )
        )

    except InvalidId:
        return jsonify({
            "success":
                False,

            "message":
                "Invalid task ID."
        }), 400

    if not deleted:
        return jsonify({
            "success":
                False,

            "message":
                "Repeat Until Done task "
                "not found."
        }), 404

    return jsonify({
        "success":
            True,

        "message":
            "Repeat Until Done task "
            "deleted successfully."
    }), 200
