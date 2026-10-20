from __future__ import annotations

import base64
import json
import os

from aah.app import create_app
from aah.config import Settings
import subprocess

from aah.crypto import (
    HKDF_INFO,
    derive_v2_aes_key,
    encrypt,
    generate_x25519_keypair,
    looks_encrypted,
    looks_v2,
    open_v2,
    parse_v2_envelope,
    seal_v2,
    validate_message_crypto,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
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


def test_v2_seal_open_roundtrip():
    private, public = generate_x25519_keypair()
    envelope = seal_v2(
        recipient_public_key=public,
        plaintext="auto negotiated",
        sender_agent_id="sender-1",
    )
    assert looks_v2(envelope)
    assert looks_encrypted(envelope)
    parse_v2_envelope(envelope)
    validate_message_crypto(
        envelope,
        agent_id="sender-1",
        key=None,
        require_encryption=True,
        to_agent_id="receiver-1",
        peer_key_exists=True,
    )
    assert (
        open_v2(
            recipient_private_key=private,
            envelope=envelope,
            sender_agent_id="sender-1",
        )
        == "auto negotiated"
    )


def test_v2_hkdf_info_is_aah_v2():
    assert HKDF_INFO == b"aah-v2"
    a_priv, a_pub = generate_x25519_keypair()
    b_priv, b_pub = generate_x25519_keypair()
    ka = derive_v2_aes_key(X25519PrivateKey.from_private_bytes(a_priv), b_pub)
    kb = derive_v2_aes_key(X25519PrivateKey.from_private_bytes(b_priv), a_pub)
    assert ka == kb
    assert len(ka) == 32


def test_malformed_v2_envelope():
    try:
        parse_v2_envelope("enc:v2:x25519-aes-256-gcm:not-enough")
    except AppError as exc:
        assert exc.code == "invalid_ciphertext"
    else:
        raise AssertionError("expected invalid_ciphertext")


def test_cli_generate_seal_open():
    gen = subprocess.run(
        ["python3", "-m", "aah.crypto", "generate", "--agent-id", "cli-peer"],
        check=True,
        capture_output=True,
        text=True,
    )
    pair = json.loads(gen.stdout)
    sealed = subprocess.run(
        [
            "python3",
            "-m",
            "aah.crypto",
            "seal",
            "--to-public-key",
            pair["public_key"],
            "--from-agent-id",
            "cli-sender",
            "--message",
            "from cli",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    envelope = sealed.stdout.strip()
    opened = subprocess.run(
        [
            "python3",
            "-m",
            "aah.crypto",
            "open",
            "--private-key",
            pair["private_key"],
            "--envelope",
            envelope,
            "--from-agent-id",
            "cli-sender",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert opened.stdout.strip() == "from cli"


def test_encrypted_without_key_is_400(client):
    key = _key()
    token = encrypt(key, "classified", associated_data="agent-alpha")
    response = client.post(
        "/api/v1/messages",
        json=sample_message(content=token),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "encryption_not_configured"
