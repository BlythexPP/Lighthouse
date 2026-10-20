from __future__ import annotations

from aah.crypto import b64encode, generate_x25519_keypair, open_v2, seal_v2
from tests.conftest import sample_message


def test_put_and_get_key(client):
    _private, public = generate_x25519_keypair()
    encoded = b64encode(public)
    created = client.put(
        "/api/v1/keys",
        json={"agent_id": "peer-a", "public_key": encoded.rstrip("=")},
    )
    assert created.status_code == 200
    assert created.json()["agent_id"] == "peer-a"
    assert created.json()["public_key"] == encoded
    fetched = client.get("/api/v1/keys/peer-a")
    assert fetched.status_code == 200
    assert fetched.json()["public_key"] == encoded


def test_missing_key_is_404(client):
    response = client.get("/api/v1/keys/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_public_key_is_400(client):
    response = client.put(
        "/api/v1/keys",
        json={"agent_id": "peer-a", "public_key": "not-a-key"},
    )
    assert response.status_code == 400


def test_v2_roundtrip_is_stored_not_decrypted(client):
    recipient_private, recipient_public = generate_x25519_keypair()
    client.put(
        "/api/v1/keys",
        json={"agent_id": "peer-b", "public_key": b64encode(recipient_public)},
    )
    envelope = seal_v2(
        recipient_public_key=recipient_public,
        plaintext="secret hello",
        sender_agent_id="peer-a",
    )
    posted = client.post(
        "/api/v1/messages",
        json=sample_message(
            agent_id="peer-a",
            payload={"content": envelope, "to_agent_id": "peer-b"},
        ),
    )
    assert posted.status_code == 202
    message_id = posted.json()["message_id"]
    fetched = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    stored = fetched.json()["responses"][0]["payload"]["content"]
    assert stored == envelope
    assert open_v2(
        recipient_private_key=recipient_private,
        envelope=stored,
        sender_agent_id="peer-a",
    ) == "secret hello"


def test_v2_without_peer_key_is_rejected(client):
    _private, public = generate_x25519_keypair()
    envelope = seal_v2(
        recipient_public_key=public,
        plaintext="secret hello",
        sender_agent_id="peer-a",
    )
    response = client.post(
        "/api/v1/messages",
        json=sample_message(
            agent_id="peer-a",
            payload={"content": envelope, "to_agent_id": "unknown-peer"},
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "peer_key_missing"


def test_plaintext_hello_allowed_when_peer_has_no_key(client):
    response = client.post(
        "/api/v1/messages",
        json=sample_message(
            agent_id="peer-a",
            payload={"content": "hello, please publish your key", "to_agent_id": "new-peer"},
        ),
    )
    assert response.status_code == 202
