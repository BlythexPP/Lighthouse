from __future__ import annotations

from tests.conftest import name_header, sample_message


def test_post_without_any_auth_headers_is_accepted(client):
    response = client.post("/api/v1/messages", json=sample_message())
    assert response.status_code == 202
    assert response.json()["status"] == "received"


def test_get_responses_without_auth_headers(client):
    created = client.post("/api/v1/messages", json=sample_message())
    message_id = created.json()["message_id"]
    listed = client.get("/api/v1/messages/responses")
    assert listed.status_code == 200
    filtered = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert filtered.status_code == 200
    assert filtered.json()["responses"][0]["message_id"] == message_id


def test_secret_header_is_ignored_and_not_required(client):
    response = client.post(
        "/api/v1/messages",
        json=sample_message(),
        headers={"X-Agent-Client-Secret": "this-is-not-checked"},
    )
    assert response.status_code == 202


def test_identifier_is_optional_name_only(client):
    named = client.post(
        "/api/v1/messages",
        json=sample_message(),
        headers=name_header("agent-one"),
    )
    anonymous = client.post("/api/v1/messages", json=sample_message())
    assert named.status_code == 202
    assert anonymous.status_code == 202


def test_no_route_returns_401_for_missing_credentials(client):
    for method, path in (
        ("POST", "/api/v1/messages"),
        ("GET", "/api/v1/messages/responses"),
    ):
        response = client.request(
            method,
            path,
            json=sample_message() if method == "POST" else None,
        )
        assert response.status_code != 401, path
        assert response.json().get("error", {}).get("code") != "unauthorized"
