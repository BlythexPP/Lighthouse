from __future__ import annotations

import tomllib
from pathlib import Path


def test_fly_toml_healthcheck_binds_public_port_without_secrets():
    raw = Path("fly.toml").read_text(encoding="utf-8")
    assert "discord.com/api/webhooks" not in raw
    config = tomllib.loads(raw)
    env = config.get("env", {})
    assert "AAH_WEBHOOK_URL" not in env
    assert "FLY_API_TOKEN" not in env
    assert config["app"] == "lighthouse-aah"
    assert config["build"]["dockerfile"] == "Dockerfile"
    assert Path("Dockerfile").is_file()
    assert Path("fly.toml").is_file()
    assert config["http_service"]["internal_port"] == 8080
    assert env["AAH_HOST"] == "0.0.0.0"
    assert env["AAH_PORT"] == "8080"
    checks = config["http_service"]["checks"]
    assert any(item.get("path") == "/healthz" and item.get("method") == "GET" for item in checks)


def test_dockerfile_healthcheck_uses_healthz():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "/healthz" in dockerfile
    assert "0.0.0.0" in dockerfile
    assert "AAH_PORT=8080" in dockerfile
    assert "COPY dashboard" in dockerfile
    assert "discord.com/api/webhooks" not in dockerfile
