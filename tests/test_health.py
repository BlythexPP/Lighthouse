from __future__ import annotations


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "Public Agent Relay"


def test_readyz_reports_database_and_webhook_flag(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["webhook_configured"] is True
    assert "super-secret-token" not in response.text


def test_unknown_path_is_structured_404(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
