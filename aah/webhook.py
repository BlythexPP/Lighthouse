"""Discord-incoming-webhook compatible delivery with bounded retries."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from aah.config import Settings
from aah.errors import AppError
from aah.util import sanitize_error, truncate

logger = logging.getLogger("aah.webhook")


class WebhookDeliveryError(Exception):
    pass


class WebhookClient(Protocol):
    async def deliver(self, payload: dict[str, Any]) -> None: ...


def build_discord_payload(
    *,
    service_name: str,
    message_id: str,
    agent_id: str,
    message_type: str,
    agent_timestamp: str,
    received_at: str,
    content: str,
    reply_channel: str | None,
) -> dict[str, Any]:
    fields = [
        {"name": "message_id", "value": truncate(message_id, 1024), "inline": True},
        {"name": "agent_id", "value": truncate(agent_id, 1024), "inline": True},
        {"name": "message_type", "value": truncate(message_type, 1024), "inline": True},
        {
            "name": "agent_timestamp",
            "value": truncate(agent_timestamp, 1024),
            "inline": False,
        },
    ]
    if reply_channel:
        fields.append(
            {
                "name": "reply_channel",
                "value": truncate(reply_channel, 1024),
                "inline": True,
            }
        )
    return {
        "username": service_name,
        "content": truncate(f"ARS message {message_id} from {agent_id}", 2000),
        "embeds": [
            {
                "title": "Agent message",
                "description": truncate(content, 4096),
                "color": 3447003,
                "fields": fields,
                "footer": {"text": "Agent Relay Service"},
                "timestamp": received_at.replace("Z", "+00:00")
                if received_at.endswith("Z")
                else received_at,
            }
        ],
    }


class HttpWebhookClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http

    def bind_http(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def deliver(self, payload: dict[str, Any]) -> None:
        url = self._settings.webhook_url_value()
        if not url:
            raise AppError(
                503,
                "webhook_not_configured",
                "AAH_WEBHOOK_URL is not configured; cannot relay messages.",
            )
        http = self._http
        if http is None:
            raise RuntimeError("HTTP client is not bound")

        attempts = self._settings.webhook_max_retries + 1
        last_error = "unknown webhook error"
        secret_fragments = [url]
        for attempt in range(1, attempts + 1):
            try:
                response = await http.post(url, json=payload)
            except httpx.HTTPError as exc:
                last_error = sanitize_error(str(exc), secret_fragments)
                logger.warning(
                    "webhook_network_error",
                    extra={"audit": {"event": "webhook_network_error", "attempt": attempt}},
                )
            else:
                if 200 <= response.status_code < 300:
                    return
                body = truncate(response.text, 200)
                last_error = sanitize_error(
                    f"HTTP {response.status_code}: {body}", secret_fragments
                )
                if 400 <= response.status_code < 500:
                    break
            if attempt < attempts:
                delay = self._settings.webhook_retry_backoff_seconds * (2 ** (attempt - 1))
                if delay:
                    await asyncio.sleep(delay)
        raise WebhookDeliveryError(last_error)
