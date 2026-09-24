"""HTTP controllers for the Gemini assistant."""

from bson.errors import InvalidId
from flask import jsonify, request

from src.modules.assistant.credentials.service import (
    CredentialValidationError,
    get_provider_credential_status,
    list_provider_credential_statuses,
    remove_provider_api_key,
    save_provider_api_key,
    test_provider_api_key as check_provider_api_key,
)
from src.modules.assistant.credentials.utils.crypto_utils import CredentialCryptoError
from src.modules.assistant.drafts.service import AssistantDraftError
from src.modules.assistant.providers.base_provider import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.modules.assistant.service import (
    choose_task_target,
    get_assistant_status,
    preview_task_command,
    run_task_command,
    send_chat,
)
from src.modules.assistant.task_parser import TaskParserError


def _request_gemini_api_key():
    """Read the per-request Gemini key. Never log or persist it."""
    return request.headers.get("X-Gemini-Api-Key", "").strip()


def _provider_error_response(error):
    if isinstance(error, ProviderNotConfiguredError):
        return jsonify({"success": False, "message": str(error)}), 503

    if isinstance(error, ProviderRateLimitError):
        return jsonify({
            "success": False,
            "message": str(error),
            "error_code": "provider_rate_limited",
            "retryable": True,
        }), 429

    return jsonify({
        "success": False,
        "message": str(error),
        "retryable": isinstance(error, ProviderConnectionError),
    }), 502


def _draft_error_response(error):
    response = {"success": False, "message": error.message}
    if getattr(error, "errors", None):
        response["errors"] = error.errors
    return jsonify(response), error.status_code


def get_assistant_health_controller():
    return jsonify({
        "success": True,
        "data": get_assistant_status(api_key=_request_gemini_api_key()),
    }), 200


def assistant_chat_controller():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Request body is required."}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "success": False,
            "message": "message is required and must be a non-empty string.",
        }), 400

    try:
        result = send_chat(
            message=message.strip(),
            api_key=_request_gemini_api_key(),
        )
    except (
        ProviderNotConfiguredError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as error:
        return _provider_error_response(error)

    return jsonify({"success": True, "data": result}), 200


def preview_task_command_controller():
    """Parse user language into/update a server-owned task draft."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Request body is required."}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "success": False,
            "message": "message is required and must be a non-empty string.",
        }), 400

    timezone_name = data.get("timezone", "UTC")
    if not isinstance(timezone_name, str):
        return jsonify({"success": False, "message": "timezone must be a string."}), 400

    draft_id = data.get("draft_id")
    if draft_id is not None and (
        not isinstance(draft_id, str) or not draft_id.strip()
    ):
        return jsonify({"success": False, "message": "draft_id must be a string."}), 400

    try:
        result = preview_task_command(
            message=message.strip(),
            timezone_name=timezone_name.strip() or "UTC",
            api_key=_request_gemini_api_key(),
            draft_id=draft_id.strip() if isinstance(draft_id, str) else None,
        )
    except AssistantDraftError as error:
        return _draft_error_response(error)
    except TaskParserError as error:
        return jsonify({"success": False, "message": error.message}), error.status_code
    except InvalidId:
        return jsonify({"success": False, "message": "Invalid assistant draft ID."}), 400
    except (
        ProviderNotConfiguredError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as error:
        return _provider_error_response(error)

    return jsonify({"success": True, "data": result}), 200


def select_task_target_controller():
    """Select one server-provided candidate for update/delete/complete."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Request body is required."}), 400

    draft_id = data.get("draft_id")
    task_id = data.get("task_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({"success": False, "message": "draft_id is required."}), 400
    if not isinstance(task_id, str) or not task_id.strip():
        return jsonify({"success": False, "message": "task_id is required."}), 400

    try:
        result = choose_task_target(draft_id.strip(), task_id.strip())
    except AssistantDraftError as error:
        return _draft_error_response(error)
    except InvalidId:
        return jsonify({"success": False, "message": "Invalid draft or task ID."}), 400

    return jsonify({"success": True, "data": result}), 200


def execute_task_command_controller():
    """Execute only the command stored in the server draft."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Request body is required."}), 400

    draft_id = data.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return jsonify({"success": False, "message": "draft_id is required."}), 400

    confirmed = data.get("confirmed", False)
    if not isinstance(confirmed, bool):
        return jsonify({"success": False, "message": "confirmed must be true or false."}), 400

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
        return jsonify({"success": False, "message": "candidate_id must be a string."}), 400

    try:
        result = run_task_command(
            draft_id=draft_id.strip(),
            confirmed=confirmed,
            duplicate_decision=duplicate_decision,
            candidate_id=candidate_id.strip() if isinstance(candidate_id, str) else None,
        )
    except AssistantDraftError as error:
        return _draft_error_response(error)
    except InvalidId:
        return jsonify({"success": False, "message": "Invalid assistant draft ID."}), 400

    return jsonify({"success": True, "data": result}), 200


# =========================================================
# ASSISTANT PROVIDER CREDENTIALS
# =========================================================

def list_assistant_credentials_controller():
    """
    Return safe credential status for every BYOK provider.

    Raw API keys are never returned.
    """

    try:
        credentials = (
            list_provider_credential_statuses()
        )

    except CredentialValidationError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    except CredentialCryptoError:
        return jsonify({
            "success": False,
            "message": (
                "Credential encryption is not configured "
                "correctly on the server."
            )
        }), 500

    return jsonify({
        "success": True,
        "data": credentials
    }), 200


def get_assistant_credential_controller(
    provider_name
):
    """
    Return safe credential metadata for one provider.

    Example:
        {
            "provider": "gemini",
            "configured": true,
            "key_hint": "****1234"
        }
    """

    try:
        credential = (
            get_provider_credential_status(
                provider_name
            )
        )

    except CredentialValidationError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    except CredentialCryptoError:
        return jsonify({
            "success": False,
            "message": (
                "Credential encryption is not configured "
                "correctly on the server."
            )
        }), 500

    return jsonify({
        "success": True,
        "data": credential
    }), 200


def test_assistant_credential_controller(
    provider_name
):
    """
    Validate a supplied provider API key WITHOUT saving it.

    Request:
        {
            "api_key": "..."
        }

    The key is never returned in the response.
    """

    data = request.get_json(
        silent=True
    )

    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body is required."
        }), 400

    api_key = data.get(
        "api_key"
    )

    try:
        result = (
            check_provider_api_key(
                provider_name,
                api_key
            )
        )

    except CredentialValidationError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    return jsonify({
        "success": True,
        "data": result
    }), 200


def save_assistant_credential_controller(
    provider_name
):
    """
    Encrypt and save a provider API key.

    Request:
        {
            "api_key": "..."
        }

    The plaintext key is never returned.
    """

    data = request.get_json(
        silent=True
    )

    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body is required."
        }), 400

    api_key = data.get(
        "api_key"
    )

    try:
        credential = (
            save_provider_api_key(
                provider_name,
                api_key
            )
        )

    except CredentialValidationError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    except CredentialCryptoError:
        return jsonify({
            "success": False,
            "message": (
                "Credential encryption is not configured "
                "correctly on the server."
            )
        }), 500

    return jsonify({
        "success": True,
        "message": (
            "Provider credential saved successfully."
        ),
        "data": credential
    }), 200


def delete_assistant_credential_controller(
    provider_name
):
    """
    Delete one stored provider API key.
    """

    try:
        deleted = (
            remove_provider_api_key(
                provider_name
            )
        )

    except CredentialValidationError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    if not deleted:
        return jsonify({
            "success": False,
            "message": (
                "Provider credential is not configured."
            )
        }), 404

    return jsonify({
        "success": True,
        "message": (
            "Provider credential deleted successfully."
        )
    }), 200
