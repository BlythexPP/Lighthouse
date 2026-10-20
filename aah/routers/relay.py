"""Open ingress: validate, persist, and relay payload.content. No API keys."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import RedirectResponse

from aah.audit import emit
from aah.auth import optional_agent_name
from aah.contract import (
    IDEMPOTENCY_HEADER,
    LEGACY_INGRESS_ALIAS_PATH,
    POST_MESSAGE_PATH,
    RELAY_STATUS_FAILED,
    RELAY_STATUS_FORWARDED,
)
from aah.crypto import validate_message_crypto
from aah.errors import AppError
from aah.ratelimit import RateLimiter
from aah.schemas import MessageAccepted, MessageRequest, serialize_timestamp
from aah.store import Store
from aah.util import sanitize_error, sha256_hex
from aah.webhook import WebhookDeliveryError, build_discord_payload

router = APIRouter()


@router.post(LEGACY_INGRESS_ALIAS_PATH, include_in_schema=True, deprecated=True)
async def legacy_ingress_alias() -> RedirectResponse:
    """Clear 308 alias. Canonical ingress is POST /api/v1/messages."""
    return RedirectResponse(url=POST_MESSAGE_PATH, status_code=308)


@router.post(POST_MESSAGE_PATH, response_model=MessageAccepted, status_code=202)
async def post_message(
    request: Request,
    body: MessageRequest,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
) -> MessageAccepted:
    settings = request.app.state.settings
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check_request(request)
    caller = optional_agent_name(request)

    key = None
    if idempotency_key is not None:
        key = idempotency_key.strip()
        if not key:
            key = None
        elif len(key) > 256:
            raise AppError(
                400,
                "validation_error",
                "Idempotency-Key must be at most 256 characters.",
            )

    validate_message_crypto(
        body.payload.content,
        agent_id=body.agent_id,
        key=settings.payload_key_bytes(),
        require_encryption=settings.require_encryption,
    )

    webhook_url = settings.webhook_url_value()
    if not webhook_url:
        emit("webhook_not_configured", caller=caller)
        raise AppError(
            503,
            "webhook_not_configured",
            "AAH_WEBHOOK_URL is not configured; cannot relay messages.",
        )

    raw_body = await request.body()
    store: Store = request.app.state.store
    row, created = await store.create_message(
        client_id=caller,
        agent_id=body.agent_id,
        agent_timestamp=serialize_timestamp(body.timestamp),
        message_type=body.message_type,
        content=body.payload.content,
        reply_channel=body.payload.reply_channel,
        idempotency_key=key,
        request_hash=sha256_hex(raw_body),
    )

    if not created:
        emit("message_replayed", caller=caller, message_id=row.message_id)
        return MessageAccepted(
            status="received",
            message_id=row.message_id,
            relay_status=row.relay_status,
        )

    discord_payload = build_discord_payload(
        service_name=settings.service_name,
        message_id=row.message_id,
        agent_id=row.agent_id,
        message_type=row.message_type,
        agent_timestamp=row.agent_timestamp,
        received_at=row.received_at,
        content=row.content,
        reply_channel=row.reply_channel,
    )

    relay_status = RELAY_STATUS_FORWARDED
    error = None
    attempts = 1
    try:
        await request.app.state.webhook_client.deliver(discord_payload)
        emit("webhook_delivered", caller=caller, message_id=row.message_id)
    except WebhookDeliveryError as exc:
        relay_status = RELAY_STATUS_FAILED
        error = sanitize_error(str(exc), [webhook_url])
        attempts = settings.webhook_max_retries + 1
        emit("webhook_failed", caller=caller, message_id=row.message_id)
    except AppError:
        raise

    await store.update_delivery(
        row.message_id,
        status=relay_status,
        attempts=attempts,
        error=error,
    )
    emit(
        "message_accepted",
        caller=caller,
        message_id=row.message_id,
        relay_status=relay_status,
    )
    return MessageAccepted(
        status="received",
        message_id=row.message_id,
        relay_status=relay_status,
    )
