"""
Pure unit tests for AI credential encryption.
"""

import pytest

from cryptography.fernet import (
    Fernet,
)

from src.modules.assistant.credentials.utils.crypto_utils import (
    CredentialCryptoError,
    decrypt_secret,
    encrypt_secret,
)


pytestmark = pytest.mark.no_db


def test_encrypt_decrypt_round_trip(
    monkeypatch
):
    monkeypatch.setenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode(
            "utf-8"
        )
    )

    plaintext = (
        "example-secret-api-key"
    )

    encrypted = encrypt_secret(
        plaintext
    )

    assert (
        encrypted
        != plaintext
    )

    assert (
        plaintext
        not in encrypted
    )

    assert (
        decrypt_secret(
            encrypted
        )
        == plaintext
    )


def test_missing_encryption_key_rejected(
    monkeypatch
):
    monkeypatch.delenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        raising=False
    )

    with pytest.raises(
        CredentialCryptoError
    ):
        encrypt_secret(
            "secret"
        )


def test_invalid_encryption_key_rejected(
    monkeypatch
):
    monkeypatch.setenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        "not-a-valid-fernet-key"
    )

    with pytest.raises(
        CredentialCryptoError
    ):
        encrypt_secret(
            "secret"
        )
