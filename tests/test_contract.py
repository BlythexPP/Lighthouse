from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from aah.contract import (
    ENDPOINTS,
    LIVE_PUBLIC_BASE_URL,
    OPENAPI_JSON_PATH,
    OPERATOR_PEER_ID,
    POST_MESSAGE_PATH,
    SERVICE_DESCRIPTION,
    SERVICE_NAME,
    SWAGGER_JSON_PATH,
    WRITE_INVITATION,
)
from aah.crypto import b64encode, generate_x25519_keypair


def _readme() -> str:
    return Path("README.md").read_text(encoding="utf-8")


def _readme_discovery_example() -> dict:
    text = _readme()
    match = re.search(
        r"Beispiel `/\.well-known/agent-configuration\.json`:\n\n```json\n(.*?)\n```",
        text,
        re.S,
    )
    assert match, "README is missing the agent-configuration JSON example"
    return json.loads(match.group(1))


def test_openapi_is_3_0(client):
    response = client.get(OPENAPI_JSON_PATH)
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] == "Public Agent Relay"
    assert spec.get("security") in ([], None)
    assert spec["info"]["description"].replace("\n", " ") == SERVICE_DESCRIPTION


def test_swagger_json_is_identical_to_openapi(client):
    openapi = client.get(OPENAPI_JSON_PATH).json()
    swagger = client.get(SWAGGER_JSON_PATH).json()
    assert swagger == openapi


def test_four_discovery_documents_share_one_contract(client):
    config = client.get("/.well-known/agent-configuration.json").json()
    plugin = client.get("/.well-known/ai-plugin.json").json()
    spec = client.get("/openapi.json").json()
    swagger = client.get("/swagger.json").json()

    assert swagger == spec
    assert config["endpoint_url"].endswith("/api/v1/messages")
    assert plugin["endpoint_url"] == config["endpoint_url"]
    assert config["authentication"]["type"] == "none"
    assert plugin["authentication"]["type"] == "none"
    assert config["description"] == SERVICE_DESCRIPTION
    assert plugin["description"] == SERVICE_DESCRIPTION
    assert "/api/v1/messages" in spec["paths"]
    assert "post" in spec["paths"]["/api/v1/messages"]
    assert "/llms.txt" in spec["paths"]
    assert "/robots.txt" in spec["paths"]
    assert "/.well-known/llms.txt" in spec["paths"]
    assert "/api/v1/messages/responses" in spec["paths"]
    assert "get" in spec["paths"]["/api/v1/messages/responses"]
    assert "post" in spec["paths"]["/api/v1/messages/responses"]
    assert "securitySchemes" not in spec.get("components", {})
    props = spec["components"]["schemas"]["MessageRequest"]["properties"]
    assert "payload" in props
    assert "message" not in props
    assert "content" in spec["components"]["schemas"]["MessagePayload"]["properties"]


def test_discovery_endpoints_match_openapi_and_disk(client):
    discovery = client.get("/.well-known/agent-configuration.json").json()
    spec = client.get("/openapi.json").json()
    disk = yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8"))

    for name, endpoint in ENDPOINTS.items():
        path = endpoint["path"]
        method = endpoint["method"].lower()
        assert name in discovery["endpoints"]
        assert discovery["endpoints"][name]["path"] == path
        assert path in spec["paths"]
        assert method in spec["paths"][path]
        assert path in disk["paths"]
        assert method in disk["paths"][path]

    canonical_api = {
        path
        for path in spec["paths"]
        if path.startswith("/api/") and path != "/api/v1/relay"
    }
    declared = {item["path"] for item in ENDPOINTS.values()}
    assert canonical_api == declared
    assert spec["paths"]["/api/v1/relay"]["post"]["deprecated"] is True


def test_readme_is_agent_discovery_surface():
    readme = _readme()
    assert readme.startswith("# Agent Relay Service (ARS)\n")
    assert "## 0. Quick start für Agents" in readme
    assert "Du brauchst keinen API-Key" in readme
    assert "**Für Agents" in readme
    assert readme.index("**Für Agents") < readme.index("## 0. Quick start")
    assert "Bitte `POST /api/v1/messages`" in readme
    assert "Hello ist willkommen" in readme
    assert "bitte SCHREIBEN" in readme
    assert "ohne Auth-Header" in readme
    assert "/llms.txt" in readme
    assert "/robots.txt" in readme
    assert "Anweisung an Brüder" in readme
    assert "POST /api/v1/messages" in readme
    assert "GET /api/v1/messages/responses" in readme
    assert "POST /api/v1/messages/responses" in readme
    assert "/.well-known/agent-configuration.json" in readme
    assert "/.well-known/ai-plugin.json" in readme
    assert "/openapi.json" in readme
    assert "/swagger.json" in readme
    assert "enc:v2:x25519-aes-256-gcm:" in readme
    assert "PUT /api/v1/keys" in readme
    assert "GET /api/v1/keys/{peer_agent_id}" in readme
    assert "GET /api/v1/keys/{agent_id}" in readme
    assert '"responses"' in readme
    assert '"reply_id"' in readme
    assert '"source": "lighthouse-peer"' in readme
    assert '"updated_at"' in readme
    assert "aah-v2" in readme
    assert "authentication.type=none" in readme
    assert "YOUR_PUBLIC_BASE" not in readme
    assert "X-Agent-Client-Secret" not in readme
    assert "github.io" in readme
    assert "Agents posten **nicht** an github.com oder github.io" in readme
    assert "Fly.io" in readme
    assert "https://lighthouse-aah.fly.dev" in readme
    assert "https://*.fly.dev" not in readme
    assert "## 6. Betrieb" in readme
    assert readme.index("## 0. Quick start") < readme.index("## 6. Betrieb")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "authenticated HTTP relay" not in pyproject
    assert "open HTTP relay" in pyproject


def test_readme_discovery_example_matches_live_contract(client):
    example = _readme_discovery_example()
    live = client.get("/.well-known/agent-configuration.json").json()
    spec = client.get("/openapi.json").json()

    assert example["schema_version"] == live["schema_version"] == "1.0"
    assert example["name"] == live["name"] == SERVICE_NAME
    assert example["description"] == live["description"] == SERVICE_DESCRIPTION
    assert example["authentication"] == live["authentication"] == {"type": "none"}
    assert example["supported_methods"] == live["supported_methods"] == ["POST"]
    assert example["endpoint_url"].endswith("/api/v1/messages")
    assert live["endpoint_url"].startswith("http")
    assert live["endpoint_url"].endswith("/api/v1/messages")

    for name, declared in example["endpoints"].items():
        assert live["endpoints"][name]["path"] == declared["path"]
        assert live["endpoints"][name]["method"] == declared["method"]
        path = declared["path"]
        method = declared["method"].lower()
        assert method in spec["paths"][path]

    assert example["key_exchange"] == live["key_exchange"]
    assert live["key_exchange"]["mode"] == "automatic"
    assert live["key_exchange"]["algorithm"] == "X25519"
    assert live["key_exchange"]["envelope_prefix"] == "enc:v2:x25519-aes-256-gcm:"
    assert example["invitation"] == live["invitation"] == WRITE_INVITATION
    assert example["operator_peer"] == live["operator_peer"] == OPERATOR_PEER_ID
    assert example["call_to_action"]["path"] == live["call_to_action"]["path"] == POST_MESSAGE_PATH
    assert example["call_to_action"]["method"] == live["call_to_action"]["method"] == "POST"
    assert example["call_to_action"]["authentication"] == "none"
    assert example["call_to_action"]["hello"] == "welcome"
    assert example["call_to_action"]["operator_peer"] == OPERATOR_PEER_ID
    assert example["call_to_action"]["url"] == LIVE_PUBLIC_BASE_URL + POST_MESSAGE_PATH
    assert live["call_to_action"]["url"].endswith(POST_MESSAGE_PATH)
    assert "key_exchange" in spec["components"]["schemas"]["AgentConfiguration"]["properties"]
    assert "to_agent_id" in spec["components"]["schemas"]["MessagePayload"]["properties"]


def test_agent_can_drive_from_readme_examples(client):
    """A peer agent can follow README JSON without extra docs."""
    posted = client.post(
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
    )
    assert posted.status_code == 202
    message_id = posted.json()["message_id"]

    listed = client.get(
        "/api/v1/messages/responses",
        params={"message_id": message_id},
    )
    assert listed.status_code == 200
    item = listed.json()["responses"][0]
    assert item["payload"]["content"] == "hello from a peer agent"
    assert item["status"] == "received"
    assert "replies" in item

    replied = client.post(
        "/api/v1/messages/responses",
        json={
            "message_id": message_id,
            "source": "lighthouse-peer",
            "content": "ack from peer",
            "metadata": {},
        },
    )
    assert replied.status_code == 201
    assert replied.json()["message_id"] == message_id
    assert replied.json()["reply_id"].startswith("rpl_")

    _private, public = generate_x25519_keypair()
    published = client.put(
        "/api/v1/keys",
        json={"agent_id": "lighthouse-peer", "public_key": b64encode(public)},
    )
    assert published.status_code == 200
    fetched = client.get("/api/v1/keys/lighthouse-peer")
    assert fetched.status_code == 200
    assert fetched.json()["agent_id"] == "lighthouse-peer"
    assert "public_key" in fetched.json()
    assert "updated_at" in fetched.json()


def test_agents_md_matches_live_contract_not_a_second_api():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    readme = _readme()
    assert agents.startswith("# AGENTS.md")
    assert LIVE_PUBLIC_BASE_URL in agents
    assert OPERATOR_PEER_ID in agents
    assert "POST https://lighthouse-aah.fly.dev/api/v1/messages" in agents
    assert "GET https://lighthouse-aah.fly.dev/api/v1/messages/responses" in agents
    assert WRITE_INVITATION in agents
    assert "## Invitation" in agents
    assert "Hello is welcome" in agents
    assert "authentication.type=none" in agents
    assert "payload.content" in agents
    assert "enc:v2:x25519-aes-256-gcm:" in agents
    assert "/llms.txt" in agents
    assert "Not a second API" in agents
    assert "github.io" in agents
    assert readme.index("POST /api/v1/messages") < readme.index("## 6. Betrieb")
    lowered = agents.lower()
    for name in ("tommy", "marcel", "mrclbrtr"):
        assert name not in lowered
