from __future__ import annotations

from aah.contract import GET_RESPONSES_PATH, POST_MESSAGE_PATH, SERVICE_DESCRIPTION, SERVICE_NAME


def test_well_known_matches_public_contract(client):
    response = client.get("/.well-known/agent-configuration.json")
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["name"] == SERVICE_NAME
    assert body["description"] == SERVICE_DESCRIPTION
    assert body["endpoint_url"] == "http://aah.test/api/v1/messages"
    assert body["supported_methods"] == ["POST"]
    assert body["authentication"] == {"type": "none"}
    assert "secret_header" not in body["authentication"]
    payload = body["endpoints"]["post_message"]["payload_structure"]
    assert payload["payload"]["content"]
    assert body["endpoints"]["post_message"]["authentication_required"] is False
    assert body["endpoints"]["post_message"]["path"] == POST_MESSAGE_PATH
    assert body["endpoints"]["get_responses"]["path"] == GET_RESPONSES_PATH


def test_ai_plugin_is_congruent_with_agent_configuration(client):
    config = client.get("/.well-known/agent-configuration.json").json()
    plugin = client.get("/.well-known/ai-plugin.json").json()
    assert plugin["name_for_human"] == config["name"]
    assert plugin["description"] == config["description"]
    assert plugin["endpoint_url"] == config["endpoint_url"]
    assert plugin["supported_methods"] == config["supported_methods"]
    assert plugin["authentication"] == config["authentication"]
    assert plugin["auth"] == {"type": "none"}
    assert plugin["endpoints"] == config["endpoints"]
    assert plugin["api"]["url"] == config["openapi"]


def test_discovery_is_unauthenticated(client):
    for path in (
        "/.well-known/agent-configuration.json",
        "/.well-known/ai-plugin.json",
        "/openapi.json",
        "/swagger.json",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Access-Control-Allow-Origin" in response.headers
