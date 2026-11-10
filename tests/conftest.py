from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from aah.app import create_app
from aah.config import Settings


class RecordingWebhook:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def deliver(self, payload: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.payloads.append(payload)


def sample_message(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "agent_id": "agent-alpha",
        "timestamp": "2026-10-20T08:50:00Z",
        "message_type": "text",
        "payload": {
            "content": "hello from lighthouse",
        },
    }
    content = overrides.pop("content", None)
    payload = overrides.pop("payload", None)
    if payload is not None:
        body["payload"] = payload
    elif content is not None:
        body["payload"] = {"content": content}
    body.update(overrides)
    return body


def name_header(name: str) -> dict[str, str]:
    return {"X-Agent-Identifier": name}


@pytest.fixture
def webhook() -> RecordingWebhook:
    return RecordingWebhook()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        public_base_url="http://aah.test",
        rate_limit_per_minute=0,
        enable_docs=True,
        webhook_require_tls=True,
        webhook_max_retries=0,
        webhook_retry_backoff_seconds=0,
    )


@pytest.fixture
def app(settings: Settings, webhook: RecordingWebhook):
    return create_app(settings, webhook_client=webhook)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
