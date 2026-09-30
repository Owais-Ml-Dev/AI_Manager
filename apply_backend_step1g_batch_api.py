from pathlib import Path
import py_compile
import shutil
import sys


def read(path):
    return path.read_text(encoding="utf-8-sig")


def write(path, text):
    path.write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = read(path)
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}")
    write(path, text.replace(old, new, 1))


def backup(path, suffix=".before_step1g.bak"):
    target = path.with_name(path.name + suffix)
    if not target.exists():
        shutil.copy2(path, target)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python apply_backend_step1g_batch_api.py <backend_dir>")

    backend = Path(sys.argv[1]).resolve()
    assistant = backend / "src/modules/assistant"
    controller = assistant / "controller.py"
    routes = assistant / "routes.py"
    tests = backend / "tests/test_assistant_task_batch_api.py"

    for path in (controller, routes):
        if not path.exists():
            raise RuntimeError(f"Missing expected file: {path}")
        backup(path)

    # ------------------------------------------------------------------
    # Controller imports
    # ------------------------------------------------------------------
    replace_once(
        controller,
        "from src.modules.assistant.credentials.service import (\n",
        "from src.modules.assistant.batch_parser import (\n"
        "    TaskBatchParserError,\n"
        "    parse_task_batch_message,\n"
        ")\n"
        "from src.modules.assistant.batches.service import (\n"
        "    AssistantBatchError,\n"
        "    cancel_active_task,\n"
        "    confirm_active_task,\n"
        "    continue_active_task,\n"
        "    create_task_batch,\n"
        "    prepare_active_task,\n"
        ")\n"
        "from src.modules.assistant.credentials.service import (\n",
    )

    # ------------------------------------------------------------------
    # Shared error response for batch workflow
    # ------------------------------------------------------------------
    replace_once(
        controller,
        "def _draft_error_response(error):\n"
        "    response = {\"success\": False, \"message\": error.message}\n"
        "    if getattr(error, \"errors\", None):\n"
        "        response[\"errors\"] = error.errors\n"
        "    return jsonify(response), error.status_code\n\n\n",
        "def _draft_error_response(error):\n"
        "    response = {\"success\": False, \"message\": error.message}\n"
        "    if getattr(error, \"errors\", None):\n"
        "        response[\"errors\"] = error.errors\n"
        "    return jsonify(response), error.status_code\n\n\n"
        "def _batch_error_response(error):\n"
        "    return jsonify({\n"
        "        \"success\": False,\n"
        "        \"message\": error.message,\n"
        "    }), error.status_code\n\n\n",
    )

    # ------------------------------------------------------------------
    # Batch HTTP controllers, inserted before provider credential section.
    # ------------------------------------------------------------------
    marker = "# =========================================================\n# ASSISTANT PROVIDER CREDENTIALS\n# =========================================================\n"
    batch_controllers = r'''# =========================================================
# MULTI-TASK BATCH WORKFLOW
# =========================================================

def start_task_batch_controller():
    """Parse one message into an ordered task batch and prepare Task 1."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "success": False,
            "message": "message is required and must be a non-empty string.",
        }), 400

    timezone_name = data.get("timezone", "UTC")
    if not isinstance(timezone_name, str):
        return jsonify({
            "success": False,
            "message": "timezone must be a string.",
        }), 400

    timezone_name = timezone_name.strip() or "UTC"

    try:
        credentials = _request_provider_credentials()
        parse_kwargs = {
            "message": message.strip(),
            "timezone_name": timezone_name,
            "api_key": _request_gemini_api_key(),
        }
        if _has_non_gemini_credentials(credentials):
            parse_kwargs["credentials"] = credentials

        parsed = parse_task_batch_message(**parse_kwargs)
        batch = create_task_batch(
            parsed,
            source_message=message.strip(),
        )
        active_task = prepare_active_task(batch["batch_id"])

    except TaskBatchParserError as error:
        return jsonify({
            "success": False,
            "message": error.message,
        }), error.status_code
    except AssistantBatchError as error:
        return _batch_error_response(error)
    except (
        ProviderNotConfiguredError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as error:
        return _provider_error_response(error)

    result = {
        **batch,
        "provider": parsed.get("provider", ""),
        "model": parsed.get("model", ""),
        "fallback_used": bool(parsed.get("fallback_used", False)),
        "attempted_providers": list(parsed.get("attempted_providers") or []),
        "active_task": active_task,
    }

    return jsonify({"success": True, "data": result}), 201


def get_active_task_batch_controller(batch_id):
    """Return/recover the current active task and its existing draft."""

    try:
        result = prepare_active_task(batch_id)
    except AssistantBatchError as error:
        return _batch_error_response(error)

    return jsonify({"success": True, "data": result}), 200


def continue_task_batch_controller(batch_id):
    """Apply one follow-up answer to the currently active batch task."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "success": False,
            "message": "message is required and must be a non-empty string.",
        }), 400

    try:
        credentials = _request_provider_credentials()
        kwargs = {
            "batch_id": batch_id,
            "message": message.strip(),
            "api_key": _request_gemini_api_key(),
        }
        if _has_non_gemini_credentials(credentials):
            kwargs["credentials"] = credentials

        result = continue_active_task(**kwargs)

    except AssistantBatchError as error:
        return _batch_error_response(error)
    except (
        ProviderNotConfiguredError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as error:
        return _provider_error_response(error)

    return jsonify({"success": True, "data": result}), 200


def confirm_task_batch_controller(batch_id):
    """Confirm and execute only the currently active batch task."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    draft_id = data.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({
            "success": False,
            "message": "draft_id is required.",
        }), 400

    duplicate_decision = data.get("duplicate_decision")
    candidate_id = data.get("candidate_id")

    if duplicate_decision is not None and duplicate_decision not in {
        "create_new",
        "update_existing",
    }:
        return jsonify({
            "success": False,
            "message": "duplicate_decision must be create_new or update_existing.",
        }), 400

    if candidate_id is not None and not isinstance(candidate_id, str):
        return jsonify({
            "success": False,
            "message": "candidate_id must be a string.",
        }), 400

    try:
        result = confirm_active_task(
            batch_id,
            draft_id.strip(),
            duplicate_decision=duplicate_decision,
            candidate_id=(
                candidate_id.strip()
                if isinstance(candidate_id, str)
                else None
            ),
        )
    except AssistantBatchError as error:
        return _batch_error_response(error)

    return jsonify({"success": True, "data": result}), 200


def cancel_task_batch_controller(batch_id):
    """Skip only the currently active batch task and prepare the next one."""

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "success": False,
            "message": "Request body is required.",
        }), 400

    draft_id = data.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({
            "success": False,
            "message": "draft_id is required.",
        }), 400

    try:
        result = cancel_active_task(
            batch_id,
            draft_id.strip(),
        )
    except AssistantBatchError as error:
        return _batch_error_response(error)

    return jsonify({"success": True, "data": result}), 200


'''

    text = read(controller)
    if marker not in text:
        raise RuntimeError(f"Controller insertion marker not found in {controller}")
    write(controller, text.replace(marker, batch_controllers + marker, 1))

    # ------------------------------------------------------------------
    # Routes imports and registrations
    # ------------------------------------------------------------------
    replace_once(
        routes,
        "    assistant_chat_controller,\n",
        "    assistant_chat_controller,\n"
        "    cancel_task_batch_controller,\n"
        "    confirm_task_batch_controller,\n"
        "    continue_task_batch_controller,\n"
        "    get_active_task_batch_controller,\n"
        "    start_task_batch_controller,\n",
    )

    route_anchor = '''assistant_bp.route("/task-command/execute", methods=["POST"])(
    execute_task_command_controller
)
'''
    route_block = route_anchor + r'''

# Ordered multi-task creation workflow.
assistant_bp.route("/task-batch/start", methods=["POST"])(
    start_task_batch_controller
)
assistant_bp.route("/task-batch/<batch_id>/active", methods=["GET"])(
    get_active_task_batch_controller
)
assistant_bp.route("/task-batch/<batch_id>/continue", methods=["POST"])(
    continue_task_batch_controller
)
assistant_bp.route("/task-batch/<batch_id>/confirm", methods=["POST"])(
    confirm_task_batch_controller
)
assistant_bp.route("/task-batch/<batch_id>/cancel", methods=["POST"])(
    cancel_task_batch_controller
)
'''
    replace_once(routes, route_anchor, route_block)

    # ------------------------------------------------------------------
    # API tests. Provider parsing is mocked; the rest uses the real test DB,
    # draft engine, validation, execution, and batch sequencing.
    # ------------------------------------------------------------------
    test_text = r'''"""Step 1G: HTTP API for the ordered multi-task batch workflow."""

import pytest

pytestmark = pytest.mark.usefixtures("app")

from src.config.db import get_db
from src.modules.assistant import controller


def _intent(title):
    return {
        "action": "create_recurring_task",
        "arguments": {
            "task": {"title": title},
            "collect": {
                "task_type_confirmed": True,
                "selected_task_action": "create_recurring_task",
            },
        },
    }


def _parsed():
    return {
        "provider": "groq",
        "type": "api",
        "model": "test-model",
        "timezone": "UTC",
        "intents": [
            _intent("Gym"),
            _intent("Call John"),
        ],
        "task_count": 2,
        "fallback_used": False,
        "attempted_providers": ["groq"],
    }


def _start(client, monkeypatch):
    monkeypatch.setattr(
        controller,
        "parse_task_batch_message",
        lambda **kwargs: _parsed(),
    )

    response = client.post(
        "/api/assistant/task-batch/start",
        json={
            "message": "Create Gym and Call John.",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def _continue_first_to_review(client, batch_id):
    answers = [
        "1 Jan 2099 to 31 Jan 2099",
        "Every day",
        "1",
        "7 am to 8 am",
        "2",
    ]

    data = None
    for answer in answers:
        response = client.post(
            f"/api/assistant/task-batch/{batch_id}/continue",
            json={"message": answer},
        )
        assert response.status_code == 200
        data = response.get_json()["data"]

    return data


def test_batch_start_requires_message(client):
    response = client.post(
        "/api/assistant/task-batch/start",
        json={"message": "   "},
    )
    assert response.status_code == 400


def test_batch_start_creates_batch_and_prepares_only_task_one(
    client,
    monkeypatch,
):
    data = _start(client, monkeypatch)

    assert data["total_tasks"] == 2
    assert data["current_task_number"] == 1
    assert data["items"][0]["status"] == "active"
    assert data["items"][1]["status"] == "pending"
    assert data["active_task"]["draft"]["status"] == "needs_input"
    assert data["active_task"]["draft"]["missing_fields"] == ["duration"]

    assert get_db().assistant_task_batches.count_documents({}) == 1
    assert get_db().assistant_drafts.count_documents({}) == 1
    assert get_db().tasks.count_documents({}) == 0


def test_active_endpoint_reuses_the_same_task_one_draft(client, monkeypatch):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    original_draft = started["active_task"]["draft"]["draft_id"]

    response = client.get(
        f"/api/assistant/task-batch/{batch_id}/active"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["draft"]["draft_id"] == original_draft
    assert get_db().assistant_drafts.count_documents({}) == 1


def test_continue_endpoint_moves_task_one_to_review(client, monkeypatch):
    started = _start(client, monkeypatch)
    data = _continue_first_to_review(client, started["batch_id"])

    assert data["current_task_number"] == 1
    assert data["draft"]["status"] in {"ready", "duplicate_review"}
    assert data["draft"]["command"]["requires_confirmation"] is True
    assert get_db().tasks.count_documents({}) == 0


def test_confirm_endpoint_executes_task_one_and_prepares_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    ready = _continue_first_to_review(client, batch_id)

    response = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": ready["draft"]["draft_id"]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolution"] == "executed"
    assert data["resolved_task_number"] == 1
    assert data["current_task_number"] == 2
    assert data["next_task"]["draft"]["status"] == "needs_input"
    assert get_db().tasks.count_documents({"title": "Gym"}) == 1
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0


def test_cancel_endpoint_skips_task_one_and_prepares_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    draft_id = started["active_task"]["draft"]["draft_id"]

    response = client.post(
        f"/api/assistant/task-batch/{batch_id}/cancel",
        json={"draft_id": draft_id},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["resolution"] == "skipped"
    assert data["resolved_task_number"] == 1
    assert data["current_task_number"] == 2
    assert data["next_task"] is not None
    assert get_db().tasks.count_documents({}) == 0


def test_stale_task_one_confirmation_cannot_confirm_task_two(
    client,
    monkeypatch,
):
    started = _start(client, monkeypatch)
    batch_id = started["batch_id"]
    ready = _continue_first_to_review(client, batch_id)
    stale_draft_id = ready["draft"]["draft_id"]

    first = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": stale_draft_id},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/assistant/task-batch/{batch_id}/confirm",
        json={"draft_id": stale_draft_id},
    )

    assert second.status_code == 409
    assert get_db().tasks.count_documents({"title": "Call John"}) == 0
'''

    write(tests, test_text)

    # Syntax-only verification; runtime tests need the project's Flask/MongoDB env.
    for path in (controller, routes, tests):
        py_compile.compile(str(path), doraise=True)

    print("Step 1G applied successfully.")
    print("Syntax check: passed")
    print("Added HTTP endpoints for the complete ordered batch flow.")


if __name__ == "__main__":
    main()
