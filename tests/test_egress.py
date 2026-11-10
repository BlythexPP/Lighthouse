from __future__ import annotations

from tests.conftest import name_header, sample_message


def test_egress_roundtrip_without_keys(client, webhook):
    created = client.post(
        "/api/v1/messages",
        json=sample_message(
            payload={"content": "hello from lighthouse", "reply_channel": "chan-1"}
        ),
    )
    assert created.status_code == 202
    message_id = created.json()["message_id"]
    assert webhook.payloads

    empty = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert empty.status_code == 200
    item = empty.json()["responses"][0]
    assert item["replies"] == []
    assert item["payload"]["content"] == "hello from lighthouse"
    assert item["payload"]["reply_channel"] == "chan-1"

    posted = client.post(
        "/api/v1/messages/responses",
        json={
            "message_id": message_id,
            "source": "discord",
            "content": "acknowledged",
            "metadata": {"channel_id": "42"},
        },
        headers=name_header("channel-bot"),
    )
    assert posted.status_code == 201
    assert posted.json()["message_id"] == message_id

    fetched = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert fetched.status_code == 200
    replies = fetched.json()["responses"][0]["replies"]
    assert len(replies) == 1
    assert replies[0]["source"] == "discord"
    assert replies[0]["content"] == "acknowledged"
    assert replies[0]["metadata"]["channel_id"] == "42"


def test_list_without_filter_returns_messages(client):
    created = client.post("/api/v1/messages", json=sample_message())
    listed = client.get("/api/v1/messages/responses")
    assert listed.status_code == 200
    ids = {item["message_id"] for item in listed.json()["responses"]}
    assert created.json()["message_id"] in ids


def test_unknown_message_is_404(client):
    response = client.get(
        "/api/v1/messages/responses",
        params={"message_id": "msg_" + ("ab" * 16)},
    )
    assert response.status_code == 404


def test_other_agents_can_read_and_reply(client):
    created = client.post(
        "/api/v1/messages",
        json=sample_message(),
        headers=name_header("agent-1"),
    )
    message_id = created.json()["message_id"]
    visible = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
        headers=name_header("agent-2"),
    )
    assert visible.status_code == 200
    reply = client.post(
        "/api/v1/messages/responses",
        json={"message_id": message_id, "source": "agent-2", "content": "pong"},
        headers=name_header("agent-2"),
    )
    assert reply.status_code == 201
    again = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert again.json()["responses"][0]["replies"][0]["content"] == "pong"


def test_reply_to_unknown_message_is_404(client):
    response = client.post(
        "/api/v1/messages/responses",
        json={
            "message_id": "msg_" + ("cd" * 16),
            "source": "discord",
            "content": "late",
        },
    )
    assert response.status_code == 404
