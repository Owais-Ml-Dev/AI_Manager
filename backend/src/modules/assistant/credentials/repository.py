"""
MongoDB repository for encrypted provider credentials.

Current design:
    one credential document per provider.

Example document:

    {
        "_id": "gemini",
        "provider": "gemini",
        "encrypted_api_key": "<ciphertext>",
        "key_hint": "****1234",
        "encryption_version": "fernet-v1"
    }

The plaintext API key is never stored.
"""

from datetime import (
    datetime,
    timezone,
)

from pymongo import ReturnDocument

from src.config.db import get_db


def find_provider_credential(
    provider_name
):
    """
    Return one encrypted credential document.
    """

    db = get_db()

    return db.assistant_credentials.find_one({
        "_id": provider_name
    })


def upsert_provider_credential(
    provider_name,
    encrypted_api_key,
    key_hint
):
    """
    Create or replace one encrypted provider credential.
    """

    db = get_db()

    now = datetime.now(
        timezone.utc
    )

    return db.assistant_credentials.find_one_and_update(
        {
            "_id": provider_name
        },
        {
            "$set": {
                "provider":
                    provider_name,

                "encrypted_api_key":
                    encrypted_api_key,

                "key_hint":
                    key_hint,

                "encryption_version":
                    "fernet-v1",

                "updated_at":
                    now,
            },

            "$setOnInsert": {
                "created_at":
                    now,
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )


def delete_provider_credential(
    provider_name
):
    """
    Delete one stored provider credential.
    """

    db = get_db()

    result = (
        db.assistant_credentials.delete_one({
            "_id": provider_name
        })
    )

    return (
        result.deleted_count
        > 0
    )

