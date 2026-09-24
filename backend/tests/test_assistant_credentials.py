"""
Tests for encrypted provider credential persistence.
"""

from cryptography.fernet import (
    Fernet,
)

from src.config.db import (
    get_db,
)

from src.modules.assistant.credentials.service import (
    get_provider_api_key,
    get_provider_credential_status,
    remove_provider_api_key,
    save_provider_api_key,
)


def _configure_test_encryption(
    monkeypatch
):
    monkeypatch.setenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode(
            "utf-8"
        )
    )


def test_api_key_is_encrypted_before_mongodb(
    client,
    monkeypatch
):
    _configure_test_encryption(
        monkeypatch
    )

    plaintext = (
        "test-super-secret-gemini-key-1234"
    )

    status = save_provider_api_key(
        "gemini",
        plaintext
    )

    assert (
        status["configured"]
        is True
    )

    assert (
        status["provider"]
        == "gemini"
    )

    assert (
        status["key_hint"]
        == "****1234"
    )

    db = get_db()

    document = (
        db.assistant_credentials.find_one({
            "_id": "gemini"
        })
    )

    assert document is not None

    assert (
        document[
            "encrypted_api_key"
        ]
        != plaintext
    )

    # The plaintext secret must not appear anywhere
    # in the persisted MongoDB document.
    assert (
        plaintext
        not in str(document)
    )

    assert (
        get_provider_api_key(
            "gemini"
        )
        == plaintext
    )


def test_status_never_returns_secret(
    client,
    monkeypatch
):
    _configure_test_encryption(
        monkeypatch
    )

    plaintext = (
        "another-secret-key-5678"
    )

    save_provider_api_key(
        "gemini",
        plaintext
    )

    status = (
        get_provider_credential_status(
            "gemini"
        )
    )

    assert (
        plaintext
        not in str(status)
    )

    assert (
        "encrypted_api_key"
        not in status
    )

    assert (
        status[
            "key_hint"
        ]
        == "****5678"
    )


def test_replacing_key_updates_secret(
    client,
    monkeypatch
):
    _configure_test_encryption(
        monkeypatch
    )

    save_provider_api_key(
        "gemini",
        "first-key-1111"
    )

    save_provider_api_key(
        "gemini",
        "second-key-2222"
    )

    assert (
        get_provider_api_key(
            "gemini"
        )
        == "second-key-2222"
    )

    status = (
        get_provider_credential_status(
            "gemini"
        )
    )

    assert (
        status[
            "key_hint"
        ]
        == "****2222"
    )


def test_missing_credential_returns_none(
    client,
    monkeypatch
):
    _configure_test_encryption(
        monkeypatch
    )

    assert (
        get_provider_api_key(
            "gemini"
        )
        is None
    )

    status = (
        get_provider_credential_status(
            "gemini"
        )
    )

    assert (
        status[
            "configured"
        ]
        is False
    )


def test_remove_provider_api_key(
    client,
    monkeypatch
):
    _configure_test_encryption(
        monkeypatch
    )

    save_provider_api_key(
        "gemini",
        "temporary-key-9999"
    )

    assert (
        remove_provider_api_key(
            "gemini"
        )
        is True
    )

    assert (
        get_provider_api_key(
            "gemini"
        )
        is None
    )
