from flask import Blueprint

from src.modules.tasks.repeat_until_done.controller import (
    create_repeat_until_done_task_controller,
    get_all_repeat_until_done_tasks_controller,
    get_repeat_until_done_task_history_controller,
    get_repeat_until_done_task_controller,
    update_repeat_until_done_task_controller,
    complete_repeat_until_done_task_controller,
    delete_repeat_until_done_task_controller
)


# =========================================================
# BLUEPRINT
# =========================================================

# Every endpoint in this module begins with:
#
# /api/tasks/repeat-until-done

repeat_until_done_task_bp = Blueprint(
    "repeat_until_done_tasks",
    __name__,
    url_prefix=(
        "/api/tasks/repeat-until-done"
    )
)


# =========================================================
# CREATE
# =========================================================
#
# POST /api/tasks/repeat-until-done

repeat_until_done_task_bp.route(
    "",
    methods=["POST"]
)(
    create_repeat_until_done_task_controller
)


# =========================================================
# GET ACTIVE TASKS
# =========================================================
#
# GET /api/tasks/repeat-until-done

repeat_until_done_task_bp.route(
    "",
    methods=["GET"]
)(
    get_all_repeat_until_done_tasks_controller
)


# =========================================================
# GET HISTORY
# =========================================================
#
# GET /api/tasks/repeat-until-done/history

repeat_until_done_task_bp.route(
    "/history",
    methods=["GET"]
)(
    get_repeat_until_done_task_history_controller
)


# =========================================================
# GET ONE
# =========================================================
#
# GET /api/tasks/repeat-until-done/<task_id>

repeat_until_done_task_bp.route(
    "/<task_id>",
    methods=["GET"]
)(
    get_repeat_until_done_task_controller
)


# =========================================================
# UPDATE
# =========================================================
#
# PATCH /api/tasks/repeat-until-done/<task_id>

repeat_until_done_task_bp.route(
    "/<task_id>",
    methods=["PATCH"]
)(
    update_repeat_until_done_task_controller
)


# =========================================================
# COMPLETE
# =========================================================
#
# PATCH
# /api/tasks/repeat-until-done/<task_id>/complete

repeat_until_done_task_bp.route(
    "/<task_id>/complete",
    methods=["PATCH"]
)(
    complete_repeat_until_done_task_controller
)


# =========================================================
# DELETE
# =========================================================
#
# DELETE /api/tasks/repeat-until-done/<task_id>

repeat_until_done_task_bp.route(
    "/<task_id>",
    methods=["DELETE"]
)(
    delete_repeat_until_done_task_controller
)
