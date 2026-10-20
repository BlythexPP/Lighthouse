from __future__ import annotations

import base64
import json
import os

from aah.app import create_app
from aah.config import Settings
from aah.crypto import encrypt, looks_encrypted, validate_message_crypto
from aah.errors import AppError
from tests.conftest import RecordingWebhook, sample_message


def _key() -> bytes:
    return os.urandom(32)


def test_compact_roundtrip():
    key = _key()
    token = encrypt(key, "secret text", associated_data="agent-alpha")
    assert looks_encrypted(token)
    validate_message_crypto(
        token, agent_id="agent-alpha", key=key, require_encryption=True
    )


def test_wrong_aad_fails():
    key = _key()
    token = encrypt(key, "secret text", associated_data="agent-alpha")
    try:
        validate_message_crypto(
            token, agent_id="other-agent", key=key, require_encryption=True
        )
    except AppError as exc:
        assert exc.code == "invalid_ciphertext"
    else:
        raise AssertionError("expected invalid_ciphertext")


def test_json_envelope_is_detected():
    envelope = json.dumps(
        {
            "enc": "AES-256-GCM",
            "iv": base64.b64encode(os.urandom(12)).decode(),
            "ciphertext": base64.b64encode(b"x").decode(),
            "tag": base64.b64encode(os.urandom(16)).decode(),
        }
    )
    assert looks_encrypted(envelope)


def test_relay_accepts_encrypted_payload_content(tmp_path):
    key = _key()
    token = encrypt(key, "classified", associated_data="agent-alpha")
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/enc.db",
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        payload_key=base64.b64encode(key).decode(),
        require_encryption=True,
        rate_limit_per_minute=0,
        webhook_max_retries=0,
    )
    webhook = RecordingWebhook()
    app = create_app(settings, webhook_client=webhook)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/messages",
            json=sample_message(content="plaintext"),
        )
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "encryption_required"

        accepted = client.post(
            "/api/v1/messages",
            json=sample_message(content=token),
        )
        assert accepted.status_code == 202
        message_id = accepted.json()["message_id"]
        fetched = client.get(
            "/api/v1/messages/responses",
            params={"message_id": message_id},
        )
        assert fetched.json()["responses"][0]["payload"]["content"] == token


def test_encrypted_without_key_is_400(client):
    key = _key()
    token = encrypt(key, "classified", associated_data="agent-alpha")
    response = client.post(
        "/api/v1/messages",
        json=sample_message(content=token),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "encryption_not_configured"
