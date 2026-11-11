from __future__ import annotations

from pathlib import Path

from aah.contract import DASHBOARD_PATH, OPERATOR_PEER_ID


def test_dashboard_serves_german_operator_ui(client):
    response = client.get(DASHBOARD_PATH)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Noch kein Agent-Bruder hat geschrieben." in body
    assert "https://lighthouse-aah.fly.dev" in body
    assert "/api/v1/messages/responses" in body
    assert "POST /api/v1/messages" in body
    assert "X-Agent-Identifier" in body
    assert "Anweisung an Brüder" in body
    assert "to_agent_id" in body
    assert "Anweisung senden" in body
    assert "github.io" not in body
    assert "discord.com/api/webhooks" not in body
    assert "AAH_WEBHOOK_URL" not in body


def test_dashboard_html_is_in_repo():
    path = Path("dashboard/index.html")
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "Lighthouse Operator" in html
    assert "payload.content" in html
    assert 'const PEER_ID = "lighthouse-peer"' in html
    assert "POST /api/v1/messages/responses" in html
    assert "sendInstruction" in html


def test_dashboard_defaults_to_contract_peer_not_personal_names(client):
    html = client.get(DASHBOARD_PATH).text
    assert html.count(f'value="{OPERATOR_PEER_ID}"') >= 3
    assert f'agent_id: {OPERATOR_PEER_ID.upper()}' not in html
    assert "agent_id: PEER_ID" in html
    assert '"X-Agent-Identifier": PEER_ID' in html
    forbidden = ("tommy", "marcel", "mrclbrtr", "gmail.com")
    lowered = html.lower()
    for name in forbidden:
        assert f'value="{name}"' not in lowered
        assert f"agent_id\": \"{name}\"" not in lowered
        assert f'const PEER_ID = "{name}"' not in lowered


def test_unknown_api_is_still_json_404(client):
    response = client.get("/api/v1/no-dashboard")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
