"""
Encryption helpers for AI-provider credentials.

Provider API keys are encrypted using Fernet before they
are written to MongoDB.

The encryption master key comes only from:

    AI_CREDENTIAL_ENCRYPTION_KEY

That master key must remain in the backend environment and
must never be stored in MongoDB or returned by an API.
"""

import os

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)


class CredentialCryptoError(RuntimeError):
    """
    Raised when encryption configuration or decryption fails.
    """


def _get_fernet():
    """
    Build the Fernet cipher from the server-side master key.
    """

    raw_key = os.getenv(
        "AI_CREDENTIAL_ENCRYPTION_KEY",
        ""
    ).strip()

    if not raw_key:
        raise CredentialCryptoError(
            "AI_CREDENTIAL_ENCRYPTION_KEY "
            "is not configured."
        )

    try:
        return Fernet(
            raw_key.encode("utf-8")
        )

    except (
        ValueError,
        TypeError,
    ) as error:
        raise CredentialCryptoError(
            "AI_CREDENTIAL_ENCRYPTION_KEY "
            "is invalid."
        ) from error


def encrypt_secret(
    secret
):
    """
    Encrypt a plaintext secret.

    Returns:
        A UTF-8 string safe to store in MongoDB.
    """

    if not isinstance(
        secret,
        str
    ):
        raise CredentialCryptoError(
            "Secret must be a string."
        )

    if not secret:
        raise CredentialCryptoError(
            "Secret cannot be empty."
        )

    encrypted = (
        _get_fernet()
        .encrypt(
            secret.encode("utf-8")
        )
    )

    return encrypted.decode(
        "utf-8"
    )


def decrypt_secret(
    encrypted_secret
):
    """
    Decrypt a previously encrypted secret.
    """

    if not isinstance(
        encrypted_secret,
        str
    ):
        raise CredentialCryptoError(
            "Encrypted secret must be a string."
        )

    try:
        decrypted = (
            _get_fernet()
            .decrypt(
                encrypted_secret.encode(
                    "utf-8"
                )
            )
        )

    except InvalidToken as error:
        raise CredentialCryptoError(
            "Stored credential could not be decrypted."
        ) from error

    return decrypted.decode(
        "utf-8"
    )
