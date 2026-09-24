"""
Tests for credential-management business logic.

No real external API requests are made.
"""

from cryptography.fernet import (
    Fernet,
)

import pytest

from src.config.db import (
    get_db,
)

from src.modules.assistant.credentials import (
    service as credential_service,
)

from src.modules.assistant.credentials.service import (
    CredentialValidationError,
    get_provider_api_key,
    list_provider_credential_statuses,
    save_provider_api_key,
    test_provider_api_key as check_provider_api_key,
)


def _configure_encryption(
    monkeypatch
):
    monkeypatch.setenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode(
            "utf-8"
        )
    )


def test_credential_provider_list_is_safe(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    statuses = (
        list_provider_credential_statuses()
    )

    assert len(statuses) == 1

    assert (
        statuses[0]["provider"]
        == "gemini"
    )

    assert (
        statuses[0]["configured"]
        is False
    )

    assert (
        "encrypted_api_key"
        not in statuses[0]
    )



def test_gemini_test_key_success_does_not_save_key(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    secret = (
        "temporary-gemini-key-1234"
    )

    class FakeResponse:
        status_code = 200
        ok = True

    monkeypatch.setattr(
        credential_service.requests,
        "get",
        lambda *args, **kwargs:
            FakeResponse()
    )

    result = check_provider_api_key(
        "gemini",
        secret
    )

    assert (
        result["accepted"]
        is True
    )

    assert (
        result["reachable"]
        is True
    )

    # Testing the key must NOT persist it.
    assert (
        get_provider_api_key(
            "gemini"
        )
        is None
    )

    # Secret must not appear in returned metadata.
    assert (
        secret
        not in str(result)
    )

    db = get_db()

    assert (
        db.assistant_credentials.count_documents({})
        == 0
    )


def test_gemini_test_key_rejected(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    secret = (
        "bad-temporary-key"
    )

    class FakeResponse:
        status_code = 401
        ok = False

    monkeypatch.setattr(
        credential_service.requests,
        "get",
        lambda *args, **kwargs:
            FakeResponse()
    )

    result = check_provider_api_key(
        "gemini",
        secret
    )

    assert (
        result["accepted"]
        is False
    )

    assert (
        result["reachable"]
        is True
    )

    assert (
        secret
        not in str(result)
    )


def test_gemini_test_handles_network_failure(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    import requests

    def fail(
        *args,
        **kwargs
    ):
        raise requests.ConnectionError(
            "offline"
        )

    monkeypatch.setattr(
        credential_service.requests,
        "get",
        fail
    )

    result = check_provider_api_key(
        "gemini",
        "temporary-key"
    )

    assert (
        result["reachable"]
        is False
    )

    assert (
        result["accepted"]
        is False
    )
