from __future__ import annotations

import httpx
import pytest
import respx

from aah.config import Settings
from aah.webhook import HttpWebhookClient, WebhookDeliveryError, build_discord_payload


def _payload() -> dict:
    return build_discord_payload(
        service_name="Public Agent Relay",
        message_id="msg_abc",
        agent_id="agent-alpha",
        message_type="text",
        agent_timestamp="2026-10-20T08:50:00Z",
        received_at="2026-10-20T08:50:01Z",
        content="hello",
        reply_channel=None,
    )


@pytest.mark.asyncio
async def test_http_webhook_success_and_retry():
    settings = Settings(
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        webhook_max_retries=2,
        webhook_retry_backoff_seconds=0,
    )
    url = settings.webhook_url_value()
    assert url is not None
    with respx.mock(assert_all_called=False) as router:
        route = router.post(url).mock(
            side_effect=[
                httpx.Response(500, text="try again"),
                httpx.Response(204),
            ]
        )
        async with httpx.AsyncClient() as http:
            client = HttpWebhookClient(settings, http)
            await client.deliver(_payload())
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_http_webhook_4xx_does_not_retry():
    settings = Settings(
        webhook_url="https://discord.example.invalid/api/webhooks/1/super-secret-token",
        webhook_max_retries=3,
        webhook_retry_backoff_seconds=0,
    )
    url = settings.webhook_url_value()
    assert url is not None
    with respx.mock() as router:
        route = router.post(url).mock(return_value=httpx.Response(401, text="bad token"))
        async with httpx.AsyncClient() as http:
            client = HttpWebhookClient(settings, http)
            with pytest.raises(WebhookDeliveryError) as exc:
                await client.deliver(_payload())
        assert route.call_count == 1
        assert "super-secret-token" not in str(exc.value)


def test_discord_payload_uses_content_and_truncates():
    payload = build_discord_payload(
        service_name="Public Agent Relay",
        message_id="msg_abc",
        agent_id="agent-alpha",
        message_type="text",
        agent_timestamp="2026-10-20T08:50:00Z",
        received_at="2026-10-20T08:50:01Z",
        content="m" * 10_000,
        reply_channel="chan-9",
    )
    assert len(payload["embeds"][0]["description"]) <= 4096
    fields = {item["name"]: item["value"] for item in payload["embeds"][0]["fields"]}
    assert fields["message_id"] == "msg_abc"
    assert fields["reply_channel"] == "chan-9"
