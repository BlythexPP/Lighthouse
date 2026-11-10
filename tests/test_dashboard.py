from __future__ import annotations

from pathlib import Path

from aah.contract import DASHBOARD_PATH


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
    assert "github.io" not in body
    assert "discord.com/api/webhooks" not in body
    assert "AAH_WEBHOOK_URL" not in body


def test_dashboard_html_is_in_repo():
    path = Path("dashboard/index.html")
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "Lighthouse Operator" in html
    assert "payload.content" in html


def test_unknown_api_is_still_json_404(client):
    response = client.get("/api/v1/no-dashboard")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
