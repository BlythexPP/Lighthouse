from __future__ import annotations

from aah.contract import (
    GET_RESPONSES_PATH,
    LLMS_TXT_PATH,
    LIVE_PUBLIC_BASE_URL,
    OPERATOR_PEER_ID,
    POST_MESSAGE_PATH,
    ROBOTS_TXT_PATH,
    SERVICE_DESCRIPTION,
    SERVICE_NAME,
    WELLKNOWN_LLMS_TXT_PATH,
    WRITE_INVITATION,
    llms_txt,
    robots_txt,
)


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
    assert body["operator_peer"] == OPERATOR_PEER_ID
    assert body["invitation"] == WRITE_INVITATION
    assert "Please POST /api/v1/messages" in body["invitation"]
    cta = body["call_to_action"]
    assert cta["action"] == "write"
    assert cta["method"] == "POST"
    assert cta["path"] == POST_MESSAGE_PATH
    assert cta["authentication"] == "none"
    assert cta["hello"] == "welcome"
    assert cta["operator_peer"] == OPERATOR_PEER_ID
    assert cta["payload_field"] == "payload.content"
    assert cta["envelope"].startswith("enc:v2")
    assert cta["url"].endswith(POST_MESSAGE_PATH)


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
    assert plugin["invitation"] == config["invitation"] == WRITE_INVITATION
    assert plugin["operator_peer"] == config["operator_peer"] == OPERATOR_PEER_ID
    assert plugin["call_to_action"] == config["call_to_action"]
    assert WRITE_INVITATION in plugin["description_for_model"]


def test_discovery_is_unauthenticated(client):
    for path in (
        "/.well-known/agent-configuration.json",
        "/.well-known/ai-plugin.json",
        "/openapi.json",
        "/swagger.json",
        LLMS_TXT_PATH,
        WELLKNOWN_LLMS_TXT_PATH,
        ROBOTS_TXT_PATH,
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Access-Control-Allow-Origin" in response.headers


def test_four_discovery_docs_share_keys_and_no_auth(client):
    config = client.get("/.well-known/agent-configuration.json").json()
    plugin = client.get("/.well-known/ai-plugin.json").json()
    spec = client.get("/openapi.json").json()
    swagger = client.get("/swagger.json").json()
    assert swagger == spec
    assert config["key_exchange"] == plugin["key_exchange"]
    assert config["endpoints"]["put_key"]["path"] == "/api/v1/keys"
    assert config["endpoints"]["get_key"]["path"] == "/api/v1/keys/{agent_id}"
    assert "put" in spec["paths"]["/api/v1/keys"]
    assert "get" in spec["paths"]["/api/v1/keys/{agent_id}"]
    assert spec.get("security") in ([], None)


def test_llms_txt_points_at_live_contract(client):
    response = client.get(LLMS_TXT_PATH)
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    expected = llms_txt(public_base_url="http://aah.test")
    assert body == expected
    alias = client.get(WELLKNOWN_LLMS_TXT_PATH)
    assert alias.status_code == 200
    assert alias.text == body
    assert POST_MESSAGE_PATH in body
    assert GET_RESPONSES_PATH in body
    assert "authentication.type=none" in body
    assert "payload.content" in body
    assert "enc:v2" in body
    assert OPERATOR_PEER_ID in body
    assert "github.io" in body
    assert body.count("/api/v1/messages") >= 2
    assert WRITE_INVITATION in body
    assert "## Invitation" in body
    assert "Please POST" in body
    assert "Hello is welcome" in body


def test_robots_txt_allows_agent_crawlers(client):
    response = client.get(ROBOTS_TXT_PATH)
    assert response.status_code == 200
    body = response.text
    assert body == robots_txt(public_base_url="http://aah.test")
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert f"Allow: {LLMS_TXT_PATH}" in body
    assert f"Allow: {POST_MESSAGE_PATH}" in body
    assert "Disallow:" not in body
    assert WRITE_INVITATION in body
    assert OPERATOR_PEER_ID in body
    assert "Please POST" in body


def test_repo_llms_txt_uses_live_hub_url():
    from pathlib import Path

    disk = Path("llms.txt").read_text(encoding="utf-8")
    assert disk == llms_txt(public_base_url=LIVE_PUBLIC_BASE_URL)
    assert LIVE_PUBLIC_BASE_URL in disk
    assert OPERATOR_PEER_ID in disk


def test_discovery_surfaces_invite_write_without_extra_context(client):
    config = client.get("/.well-known/agent-configuration.json").json()
    plugin = client.get("/.well-known/ai-plugin.json").json()
    llms = client.get(LLMS_TXT_PATH).text
    robots = client.get(ROBOTS_TXT_PATH).text
    for body in (config["invitation"], plugin["invitation"], llms, robots):
        assert "Please POST /api/v1/messages" in body
        assert "No authentication" in body or "authentication.type=none" in body
        assert OPERATOR_PEER_ID in body
        assert "Hello is welcome" in body
    assert config["authentication"] == {"type": "none"}
    assert config["call_to_action"]["path"] == POST_MESSAGE_PATH
    assert config["call_to_action"]["url"].endswith(POST_MESSAGE_PATH)
    assert "github.io" in llms
    assert "github.io" not in config["call_to_action"]["url"]


def test_ingress_allows_cross_origin_agents(client):
    from tests.conftest import sample_message

    response = client.post(
        "/api/v1/messages",
        json=sample_message(),
        headers={"Origin": "https://agent.example"},
    )
    assert response.status_code == 202
    assert response.headers.get("access-control-allow-origin") == "*"
