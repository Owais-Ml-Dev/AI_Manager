"""Gemini assistant API routes."""

from flask import Blueprint

from src.modules.assistant.controller import (
    assistant_chat_controller,
    delete_assistant_credential_controller,
    execute_task_command_controller,
    get_assistant_credential_controller,
    get_assistant_health_controller,
    list_assistant_credentials_controller,
    preview_task_command_controller,
    select_task_target_controller,
    save_assistant_credential_controller,
    test_assistant_credential_controller,
)


assistant_bp = Blueprint(
    "assistant",
    __name__,
    url_prefix="/api/assistant",
)

assistant_bp.route("/health", methods=["GET"])(
    get_assistant_health_controller
)

assistant_bp.route("/credentials", methods=["GET"])(
    list_assistant_credentials_controller
)
assistant_bp.route("/credentials/<provider_name>/test", methods=["POST"])(
    test_assistant_credential_controller
)
assistant_bp.route("/credentials/<provider_name>", methods=["GET"])(
    get_assistant_credential_controller
)
assistant_bp.route("/credentials/<provider_name>", methods=["PUT"])(
    save_assistant_credential_controller
)
assistant_bp.route("/credentials/<provider_name>", methods=["DELETE"])(
    delete_assistant_credential_controller
)

assistant_bp.route("/chat", methods=["POST"])(
    assistant_chat_controller
)
assistant_bp.route("/task-command/preview", methods=["POST"])(
    preview_task_command_controller
)
assistant_bp.route("/task-command/select-target", methods=["POST"])(
    select_task_target_controller
)
assistant_bp.route("/task-command/execute", methods=["POST"])(
    execute_task_command_controller
)
