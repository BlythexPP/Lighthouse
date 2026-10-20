from __future__ import annotations

from aah.app import create_app
from aah.config import Settings
from aah.webhook import WebhookDeliveryError
from tests.conftest import sample_message


def test_readme_quickstart_example_is_accepted(client, webhook):
    response = client.post(
        "/api/v1/messages",
        json={
            "agent_id": "lighthouse-peer",
            "timestamp": "2026-10-20T09:38:00Z",
            "message_type": "text",
            "payload": {
                "content": "hello from a peer agent",
                "reply_channel": None,
            },
        },
        headers={"X-Agent-Identifier": "lighthouse-peer"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "received"
    assert body["relay_status"] == "forwarded_to_webhook"
    assert body["message_id"].startswith("msg_")
    fetched = client.get(
        "/api/v1/messages/responses",
        params={"message_id": body["message_id"]},
    )
    assert fetched.status_code == 200
    assert fetched.json()["responses"][0]["payload"]["content"] == "hello from a peer agent"


def test_valid_message_returns_202_and_calls_webhook(client, webhook):
    response = client.post("/api/v1/messages", json=sample_message())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "received"
    assert body["relay_status"] == "forwarded_to_webhook"
    assert body["message_id"].startswith("msg_")
    assert len(webhook.payloads) == 1
    payload = webhook.payloads[0]
    assert payload["username"] == "Public Agent Relay"
    fields = {item["name"]: item["value"] for item in payload["embeds"][0]["fields"]}
    assert fields["message_id"] == body["message_id"]
    assert fields["agent_id"] == "agent-alpha"
    assert fields["message_type"] == "text"
    assert "hello from lighthouse" in payload["embeds"][0]["description"]
    assert "super-secret-token" not in response.text


def test_legacy_relay_path_is_308_alias(client, webhook):
    response = client.post(
        "/api/v1/relay",
        json=sample_message(),
        follow_redirects=False,
    )
    assert response.status_code == 308
    assert response.headers["location"].endswith("/api/v1/messages")
    assert webhook.payloads == []

    followed = client.post(
        "/api/v1/relay",
        json=sample_message(),
        follow_redirects=True,
    )
    assert followed.status_code == 202
    assert followed.json()["status"] == "received"
    assert len(webhook.payloads) == 1


def test_invalid_schema_is_400(client):
    body = sample_message()
    body["timestamp"] = "not-a-timestamp"
    response = client.post("/api/v1/messages", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_message_type_is_400(client):
    response = client.post(
        "/api/v1/messages",
        json=sample_message(message_type="active"),
    )
    assert response.status_code == 400


def test_legacy_message_field_is_rejected(client):
    body = {
        "agent_id": "agent-alpha",
        "timestamp": "2026-10-20T08:50:00Z",
        "status": "active",
        "payload_type": "text/plain",
        "message": "legacy",
    }
    response = client.post("/api/v1/messages", json=body)
    assert response.status_code == 400


def test_webhook_failure_still_accepts_message(client, webhook):
    webhook.error = WebhookDeliveryError("HTTP 500: boom")
    response = client.post("/api/v1/messages", json=sample_message())
    assert response.status_code == 202
    assert response.json()["relay_status"] == "webhook_failed"
    message_id = response.json()["message_id"]
    fetched = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert fetched.status_code == 200
    assert fetched.json()["responses"][0]["relay_status"] == "webhook_failed"


def test_missing_webhook_is_503(tmp_path, webhook):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/nowebhook.db",
        webhook_url=None,
        rate_limit_per_minute=0,
        webhook_require_tls=False,
    )
    app = create_app(settings, webhook_client=webhook)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/messages", json=sample_message())
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "webhook_not_configured"
        assert len(webhook.payloads) == 0


def test_idempotency_replay_returns_same_message(client, webhook):
    headers = {"Idempotency-Key": "once-only"}
    first = client.post("/api/v1/messages", json=sample_message(), headers=headers)
    second = client.post("/api/v1/messages", json=sample_message(), headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["message_id"] == second.json()["message_id"]
    assert len(webhook.payloads) == 1


def test_idempotency_conflict(client):
    headers = {"Idempotency-Key": "once-only"}
    first = client.post("/api/v1/messages", json=sample_message(), headers=headers)
    assert first.status_code == 202
    conflict = client.post(
        "/api/v1/messages",
        json=sample_message(content="different"),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_payload_too_large(tmp_path, webhook):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/small.db",
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        max_body_bytes=1024,
        rate_limit_per_minute=0,
    )
    app = create_app(settings, webhook_client=webhook)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/messages",
            json=sample_message(content="x" * 4000),
        )
        assert response.status_code == 413


def test_rate_limit(tmp_path, webhook):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/rl.db",
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        rate_limit_per_minute=1,
        webhook_max_retries=0,
    )
    app = create_app(settings, webhook_client=webhook)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        ok = test_client.post("/api/v1/messages", json=sample_message())
        limited = test_client.post("/api/v1/messages", json=sample_message())
        assert ok.status_code == 202
        assert limited.status_code == 429
        assert limited.headers["Retry-After"]
        assert limited.json()["error"]["code"] == "rate_limited"
