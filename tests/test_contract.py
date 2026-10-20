from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from aah.contract import ENDPOINTS, OPENAPI_JSON_PATH, SERVICE_DESCRIPTION, SERVICE_NAME, SWAGGER_JSON_PATH


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
    assert "ohne Auth-Header" in readme
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
    assert "aah-v2" in readme
    assert "authentication.type=none" in readme
    assert "YOUR_PUBLIC_BASE" not in readme
    assert "X-Agent-Client-Secret" not in readme
    assert "github.io" in readme
    assert "Agents posten **nicht** an github.com oder github.io" in readme
    assert "Fly.io" in readme
    assert "https://*.fly.dev" in readme
    assert "lighthouse-aah.fly.dev" not in readme
    assert "## 6. Betrieb" in readme
    assert readme.index("## 0. Quick start") < readme.index("## 6. Betrieb")


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
