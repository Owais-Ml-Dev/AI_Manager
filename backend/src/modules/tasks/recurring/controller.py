from bson.errors import InvalidId
from flask import jsonify, request

from src.modules.tasks.recurring.service import (
    create_recurring_task,
    get_all_recurring_tasks,
    get_recurring_task_history,
    get_recurring_task_details,
    get_recurring_task,
    update_recurring_task,
    get_recurring_task_occurrences,
    get_recurring_occurrence,
    complete_recurring_occurrence,
    complete_recurring_task,
    delete_recurring_task
)

from src.modules.tasks.recurring.validation import (
    validate_create_recurring_task,
    validate_update_recurring_task
)

def create_recurring_task_controller():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required."
        }), 400

    errors = validate_create_recurring_task(data)

    if errors:
        return jsonify({
            "success": False,
            "message": "Validation failed.",
            "errors": errors
        }), 400

    result = create_recurring_task(data)

    return jsonify({
        "success": True,
        "message": "Recurring task created successfully.",
        "data": result
    }), 201

def get_all_recurring_tasks_controller():
    tasks = get_all_recurring_tasks()

    return jsonify({
        "success": True,
        "count": len(tasks),
        "data": tasks
    }), 200

def get_recurring_task_history_controller():
    """
    Return ended recurring parent tasks with their summary
    statistics for the recurring History screen.
    """

    history = get_recurring_task_history()

    return jsonify({
        "success": True,
        "count": len(history),
        "data": history
    }), 200


def get_recurring_task_details_controller(task_id):
    """
    Return recurring task detail data for either an active
    task or an ended task opened from History.
    """

    try:
        details = get_recurring_task_details(
            task_id
        )
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    if details is None:
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    return jsonify({
        "success": True,
        "data": details
    }), 200


def get_recurring_task_controller(task_id):
    try:
        task = get_recurring_task(task_id)
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    if task is None:
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    return jsonify({
        "success": True,
        "data": task
    }), 200

def update_recurring_task_controller(task_id):
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required."
        }), 400

    try:
        current_task = get_recurring_task(task_id)
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    if current_task is None:
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    errors = validate_update_recurring_task(
        data,
        current_task
    )

    if errors:
        return jsonify({
            "success": False,
            "message": "Validation failed.",
            "errors": errors
        }), 400

    result = update_recurring_task(
        task_id,
        data
    )

    if result == "not_found":
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    if result == "inactive":
        return jsonify({
            "success": False,
            "message": (
                "Inactive recurring tasks cannot be updated."
            )
        }), 409

    return jsonify({
        "success": True,
        "message": "Recurring task updated successfully.",
        "data": result
    }), 200

def get_recurring_task_occurrences_controller(task_id):
    try:
        task = get_recurring_task(task_id)

        if task is None:
            return jsonify({
                "success": False,
                "message": "Recurring task not found."
            }), 404

        occurrences = get_recurring_task_occurrences(
            task_id
        )

    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    return jsonify({
        "success": True,
        "count": len(occurrences),
        "data": occurrences
    }), 200

def get_recurring_occurrence_controller(occurrence_id):
    try:
        occurrence = get_recurring_occurrence(
            occurrence_id
        )
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid occurrence ID."
        }), 400

    if occurrence is None:
        return jsonify({
            "success": False,
            "message": "Recurring occurrence not found."
        }), 404

    return jsonify({
        "success": True,
        "data": occurrence
    }), 200

def complete_recurring_occurrence_controller(occurrence_id):
    try:
        result = complete_recurring_occurrence(
            occurrence_id
        )
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid occurrence ID."
        }), 400

    if result == "not_found":
        return jsonify({
            "success": False,
            "message": "Recurring occurrence not found."
        }), 404

    if result == "already_completed":
        return jsonify({
            "success": False,
            "message": (
                "This recurring occurrence is already completed."
            )
        }), 409

    if result == "missed":
        return jsonify({
            "success": False,
            "message": (
                "A missed recurring occurrence cannot be completed."
            )
        }), 409

    if result == "already_processed":
        return jsonify({
            "success": False,
            "message": (
                "This recurring occurrence has already been processed."
            )
        }), 409

    return jsonify({
        "success": True,
        "message": (
            "Recurring occurrence completed successfully."
        ),
        "data": result
    }), 200

def complete_recurring_task_controller(
    task_id
):
    try:
        result = complete_recurring_task(
            task_id
        )
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    if result == "not_found":
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    if result == "already_ended":
        return jsonify({
            "success": False,
            "message": (
                "This recurring task has already ended."
            )
        }), 409

    return jsonify({
        "success": True,
        "message": (
            "Recurring task completed permanently."
        ),
        "data": result
    }), 200


def delete_recurring_task_controller(task_id):
    try:
        deleted = delete_recurring_task(task_id)
    except InvalidId:
        return jsonify({
            "success": False,
            "message": "Invalid task ID."
        }), 400

    if not deleted:
        return jsonify({
            "success": False,
            "message": "Recurring task not found."
        }), 404

    return jsonify({
        "success": True,
        "message": "Recurring task deleted successfully."
    }), 200
