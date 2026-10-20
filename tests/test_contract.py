from __future__ import annotations

from pathlib import Path

import yaml

from aah.contract import ENDPOINTS, OPENAPI_JSON_PATH, SWAGGER_JSON_PATH


def test_openapi_is_3_0(client):
    response = client.get(OPENAPI_JSON_PATH)
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] == "Public Agent Relay"
    assert spec.get("security") in ([], None)


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
    assert "/api/v1/messages" in spec["paths"]
    assert "post" in spec["paths"]["/api/v1/messages"]
    assert "/api/v1/messages/responses" in spec["paths"]
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


def test_readme_contains_canonical_contract():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Agent Relay Service (ARS)\n")
    assert "POST /api/v1/messages" in readme
    assert "GET /api/v1/messages/responses" in readme
    assert "X-Agent-Identifier" in readme
    assert "keine (vorerst)" in readme
    assert "X-Agent-Client-Secret" not in readme
    assert "/.well-known/ai-plugin.json" in readme
    assert "/swagger.json" in readme
    assert "202 Accepted" in readme
