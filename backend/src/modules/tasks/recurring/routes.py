from flask import Blueprint

from src.modules.tasks.recurring.controller import (
    create_recurring_task_controller,
    get_all_recurring_tasks_controller,
    get_recurring_task_history_controller,
    get_recurring_task_details_controller,
    get_recurring_task_controller,
    update_recurring_task_controller,
    get_recurring_task_occurrences_controller,
    get_recurring_occurrence_controller,
    complete_recurring_occurrence_controller,
    complete_recurring_task_controller,
    delete_recurring_task_controller
)

recurring_task_bp = Blueprint(
    "recurring_tasks",
    __name__,
    url_prefix="/api/tasks/recurring"
)

recurring_task_bp.route(
    "",
    methods=["POST"]
)(
    create_recurring_task_controller
)

recurring_task_bp.route(
    "",
    methods=["GET"]
)(
    get_all_recurring_tasks_controller
)

# Recurring parent-task history.
recurring_task_bp.route(
    "/history",
    methods=["GET"]
)(
    get_recurring_task_history_controller
)

# Full data for the recurring task detail screen.
# Works for active and ended recurring tasks.
recurring_task_bp.route(
    "/<task_id>/details",
    methods=["GET"]
)(
    get_recurring_task_details_controller
)

recurring_task_bp.route(
    "/occurrences/<occurrence_id>",
    methods=["GET"]
)(
    get_recurring_occurrence_controller
)

recurring_task_bp.route(
    "/occurrences/<occurrence_id>/complete",
    methods=["PATCH"]
)(
    complete_recurring_occurrence_controller
)

recurring_task_bp.route(
    "/<task_id>/occurrences",
    methods=["GET"]
)(
    get_recurring_task_occurrences_controller
)

recurring_task_bp.route(
    "/<task_id>",
    methods=["GET"]
)(
    get_recurring_task_controller
)

recurring_task_bp.route(
    "/<task_id>",
    methods=["PATCH"]
)(
    update_recurring_task_controller
)

recurring_task_bp.route(
    "/<task_id>/complete",
    methods=["PATCH"]
)(
    complete_recurring_task_controller
)

recurring_task_bp.route(
    "/<task_id>",
    methods=["DELETE"]
)(
    delete_recurring_task_controller
)
