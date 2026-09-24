"""
HTTP tests for assistant BYOK credential endpoints.

No real Gemini requests are made.
"""

from cryptography.fernet import (
    Fernet,
)

from src.config.db import (
    get_db,
)

from src.modules.assistant.credentials import (
    service as credential_service,
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


def test_list_credentials(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    response = client.get(
        "/api/assistant/credentials"
    )

    assert (
        response.status_code
        == 200
    )

    data = (
        response.get_json()[
            "data"
        ]
    )

    assert len(data) == 1

    assert (
        data[0]["provider"]
        == "gemini"
    )

    assert (
        data[0]["configured"]
        is False
    )


def test_get_unconfigured_gemini_credential(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    response = client.get(
        "/api/assistant/credentials/gemini"
    )

    assert (
        response.status_code
        == 200
    )

    data = (
        response.get_json()[
            "data"
        ]
    )

    assert (
        data["provider"]
        == "gemini"
    )

    assert (
        data["configured"]
        is False
    )

    assert (
        data["key_hint"]
        is None
    )


def test_test_gemini_key_without_saving(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    secret = (
        "temporary-test-key-1234"
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

    response = client.post(
        "/api/assistant/credentials/gemini/test",
        json={
            "api_key": secret
        }
    )

    assert (
        response.status_code
        == 200
    )

    body = (
        response.get_json()
    )

    assert (
        body["data"]["accepted"]
        is True
    )

    assert (
        secret
        not in str(body)
    )

    db = get_db()

    assert (
        db.assistant_credentials.count_documents({})
        == 0
    )


def test_save_gemini_key_is_safe(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    secret = (
        "user-gemini-secret-5678"
    )

    response = client.put(
        "/api/assistant/credentials/gemini",
        json={
            "api_key": secret
        }
    )

    assert (
        response.status_code
        == 200
    )

    body = (
        response.get_json()
    )

    assert (
        body["data"]["configured"]
        is True
    )

    assert (
        body["data"]["key_hint"]
        == "****5678"
    )

    assert (
        secret
        not in str(body)
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
        != secret
    )

    assert (
        secret
        not in str(document)
    )


def test_saved_key_status_never_exposes_secret(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    secret = (
        "another-private-key-ABCD"
    )

    client.put(
        "/api/assistant/credentials/gemini",
        json={
            "api_key": secret
        }
    )

    response = client.get(
        "/api/assistant/credentials/gemini"
    )

    assert (
        response.status_code
        == 200
    )

    body = (
        response.get_json()
    )

    assert (
        secret
        not in str(body)
    )

    assert (
        body["data"]["key_hint"]
        == "****ABCD"
    )


def test_delete_gemini_key(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    client.put(
        "/api/assistant/credentials/gemini",
        json={
            "api_key":
                "temporary-secret-9999"
        }
    )

    response = client.delete(
        "/api/assistant/credentials/gemini"
    )

    assert (
        response.status_code
        == 200
    )

    response = client.get(
        "/api/assistant/credentials/gemini"
    )

    assert (
        response.get_json()[
            "data"
        ][
            "configured"
        ]
        is False
    )


def test_delete_missing_key_returns_404(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    response = client.delete(
        "/api/assistant/credentials/gemini"
    )

    assert (
        response.status_code
        == 404
    )



def test_save_requires_api_key(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    response = client.put(
        "/api/assistant/credentials/gemini",
        json={}
    )

    assert (
        response.status_code
        == 400
    )


def test_test_endpoint_requires_api_key(
    client,
    monkeypatch
):
    _configure_encryption(
        monkeypatch
    )

    response = client.post(
        "/api/assistant/credentials/gemini/test",
        json={}
    )

    assert (
        response.status_code
        == 400
    )
