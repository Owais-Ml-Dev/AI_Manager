"""
Encrypted AI-provider credential service.

Public/safe operations expose only:
    provider
    configured
    key_hint
    timestamps

Raw API keys are only decrypted internally.

BYOK-enabled provider:
    gemini
"""

import os
import re

import requests

from src.modules.assistant.credentials.repository import (
    delete_provider_credential,
    find_provider_credential,
    upsert_provider_credential,
)

from src.modules.assistant.credentials.utils.crypto_utils import (
    decrypt_secret,
    encrypt_secret,
)


# =========================================================
# PROVIDERS THAT CURRENTLY SUPPORT USER API KEYS
# =========================================================

CREDENTIAL_PROVIDERS = (
    "gemini",
)


_PROVIDER_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,63}$"
)


class CredentialValidationError(ValueError):
    """
    Raised when credential input is invalid.
    """


# =========================================================
# VALIDATION
# =========================================================

def normalize_provider_name(
    provider_name
):
    """
    Normalize a provider identifier.
    """

    if not isinstance(
        provider_name,
        str
    ):
        raise CredentialValidationError(
            "Provider name must be a string."
        )

    provider_name = (
        provider_name
        .strip()
        .lower()
    )

    if not provider_name:
        raise CredentialValidationError(
            "Provider name is required."
        )

    if not _PROVIDER_PATTERN.fullmatch(
        provider_name
    ):
        raise CredentialValidationError(
            "Provider name contains invalid characters."
        )

    return provider_name


def require_credential_provider(
    provider_name
):
    """
    Ensure this provider supports user-managed API keys.
    """

    provider_name = (
        normalize_provider_name(
            provider_name
        )
    )

    if (
        provider_name
        not in CREDENTIAL_PROVIDERS
    ):
        raise CredentialValidationError(
            f"{provider_name} does not support "
            "user-managed API credentials."
        )

    return provider_name


def validate_api_key(
    api_key
):
    """
    Validate API-key input without assuming a provider's
    exact key prefix.
    """

    if not isinstance(
        api_key,
        str
    ):
        raise CredentialValidationError(
            "API key must be a string."
        )

    api_key = api_key.strip()

    if not api_key:
        raise CredentialValidationError(
            "API key is required."
        )

    if len(api_key) > 4096:
        raise CredentialValidationError(
            "API key is too long."
        )

    return api_key


# =========================================================
# SAFE SERIALIZATION
# =========================================================

def _key_hint(
    api_key
):
    """
    Safe UI hint.

    Example:
        ABCDEFGH1234
        ->
        ****1234
    """

    if len(api_key) <= 4:
        return "****"

    return (
        "****"
        + api_key[-4:]
    )


def _serialize_status(
    document,
    provider_name
):
    """
    Return safe metadata only.

    encrypted_api_key is deliberately excluded.
    """

    if not document:
        return {
            "provider":
                provider_name,

            "configured":
                False,

            "key_hint":
                None,

            "created_at":
                None,

            "updated_at":
                None,
        }

    created_at = document.get(
        "created_at"
    )

    updated_at = document.get(
        "updated_at"
    )

    return {
        "provider":
            provider_name,

        "configured":
            True,

        "key_hint":
            document.get(
                "key_hint"
            ),

        "created_at": (
            created_at.isoformat()
            if created_at
            else None
        ),

        "updated_at": (
            updated_at.isoformat()
            if updated_at
            else None
        ),
    }


# =========================================================
# SAVE
# =========================================================

def save_provider_api_key(
    provider_name,
    api_key
):
    """
    Encrypt and save a provider API key.
    """

    provider_name = (
        require_credential_provider(
            provider_name
        )
    )

    api_key = validate_api_key(
        api_key
    )

    encrypted_api_key = (
        encrypt_secret(
            api_key
        )
    )

    document = (
        upsert_provider_credential(
            provider_name=provider_name,
            encrypted_api_key=encrypted_api_key,
            key_hint=_key_hint(
                api_key
            )
        )
    )

    # Drop any cached provider instance so the very next
    # request picks up this new API key immediately.
    # Local import avoids a factory <-> credentials cycle.
    from src.modules.assistant.providers.provider_factory import (
        invalidate_provider_cache,
    )
    invalidate_provider_cache(provider_name)

    return _serialize_status(
        document,
        provider_name
    )


# =========================================================
# INTERNAL DECRYPTION
# =========================================================

def get_provider_api_key(
    provider_name
):
    """
    INTERNAL ONLY.

    Retrieve and decrypt a provider API key.

    Never return this result from an HTTP endpoint.
    """

    provider_name = (
        require_credential_provider(
            provider_name
        )
    )

    document = (
        find_provider_credential(
            provider_name
        )
    )

    if not document:
        return None

    return decrypt_secret(
        document[
            "encrypted_api_key"
        ]
    )


# =========================================================
# SAFE STATUS
# =========================================================

def get_provider_credential_status(
    provider_name
):
    """
    Return safe credential metadata.
    """

    provider_name = (
        require_credential_provider(
            provider_name
        )
    )

    document = (
        find_provider_credential(
            provider_name
        )
    )

    return _serialize_status(
        document,
        provider_name
    )


def list_provider_credential_statuses():
    """
    Return safe status for the Gemini BYOK provider.
    """

    return [
        get_provider_credential_status(
            provider_name
        )
        for provider_name
        in CREDENTIAL_PROVIDERS
    ]


# =========================================================
# DELETE
# =========================================================

def remove_provider_api_key(
    provider_name
):
    """
    Delete one stored provider credential.
    """

    provider_name = (
        require_credential_provider(
            provider_name
        )
    )

    result = delete_provider_credential(
        provider_name
    )

    from src.modules.assistant.providers.provider_factory import (
        invalidate_provider_cache,
    )
    invalidate_provider_cache(provider_name)

    return result


# =========================================================
# TEST WITHOUT SAVING
# =========================================================

def _test_gemini_api_key(
    api_key
):
    """
    Test a Gemini API key without storing it.

    We use the lightweight models endpoint rather than
    generating content.

    Important:
        The raw key is never included in the return value.
    """

    base_url = (
        os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta"
        )
        .rstrip("/")
    )

    try:
        response = requests.get(
            f"{base_url}/models",

            headers={
                "x-goog-api-key":
                    api_key
            },

            params={
                "pageSize":
                    1
            },

            timeout=10
        )

    except requests.RequestException:
        return {
            "provider":
                "gemini",

            "reachable":
                False,

            "accepted":
                False,

            "message":
                "Gemini API is not reachable."
        }

    if response.ok:
        return {
            "provider":
                "gemini",

            "reachable":
                True,

            "accepted":
                True,

            "message":
                "Gemini API key is valid and reachable."
        }

    return {
        "provider":
            "gemini",

        "reachable":
            True,

        "accepted":
            False,

        "message": (
            "Gemini rejected the API key "
            f"(HTTP {response.status_code})."
        )
    }


def test_provider_api_key(
    provider_name,
    api_key
):
    """
    Test a supplied key WITHOUT storing it.

    The raw key never appears in the returned result.
    """

    provider_name = (
        require_credential_provider(
            provider_name
        )
    )

    api_key = validate_api_key(
        api_key
    )

    if provider_name == "gemini":
        return _test_gemini_api_key(
            api_key
        )

    # Defensive fallback for future providers.
    raise CredentialValidationError(
        f"No credential tester exists "
        f"for {provider_name}."
    )
