"""Open egress lookup and reply ingress on /api/v1/messages/responses."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Query, Request

from aah.audit import emit
from aah.auth import optional_agent_name
from aah.errors import AppError
from aah.ratelimit import RateLimiter
from aah.schemas import (
    EgressReplyAccepted,
    EgressReplyRequest,
    EgressReplyView,
    MessagePayload,
    MessageView,
    ResponsesView,
)
from aah.store import Store

router = APIRouter()

_MESSAGE_ID = re.compile(r"^msg_[0-9a-f]{32}$")


def _to_view(row) -> MessageView:
    replies = [
        EgressReplyView(
            reply_id=reply.reply_id,
            source=reply.source,
            content=reply.content,
            metadata=json.loads(reply.metadata_json),
            received_at=reply.received_at,
        )
        for reply in sorted(row.replies, key=lambda item: item.received_at)
    ]
    return MessageView(
        message_id=row.message_id,
        agent_id=row.agent_id,
        timestamp=row.agent_timestamp,
        received_at=row.received_at,
        message_type=row.message_type,
        payload=MessagePayload(
            content=row.content,
            reply_channel=row.reply_channel,
            to_agent_id=row.to_agent_id,
        ),
        status="received",
        relay_status=row.relay_status,
        replies=replies,
    )


@router.get("/api/v1/messages/responses", response_model=ResponsesView)
async def get_responses(
    request: Request,
    message_id: str | None = Query(default=None),
) -> ResponsesView:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check_request(request)
    store: Store = request.app.state.store
    caller = optional_agent_name(request)

    if message_id is not None:
        if not _MESSAGE_ID.match(message_id):
            raise AppError(400, "validation_error", "message_id is not a valid identifier.")
        row = await store.get_message(message_id)
        if row is None:
            raise AppError(404, "not_found", "Unknown message_id.")
        emit("egress_read", caller=caller, message_id=message_id)
        return ResponsesView(responses=[_to_view(row)])

    rows = await store.list_messages()
    emit("egress_list", caller=caller, count=len(rows))
    return ResponsesView(responses=[_to_view(row) for row in rows])


@router.post(
    "/api/v1/messages/responses",
    response_model=EgressReplyAccepted,
    status_code=201,
)
async def post_response(
    payload: EgressReplyRequest,
    request: Request,
) -> EgressReplyAccepted:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check_request(request)
    store: Store = request.app.state.store
    caller = optional_agent_name(request)
    row = await store.add_reply(
        message_id=payload.message_id,
        source=payload.source,
        content=payload.content,
        metadata=payload.metadata,
    )
    emit(
        "egress_reply_accepted",
        caller=caller,
        message_id=payload.message_id,
        reply_id=row.reply_id,
    )
    return EgressReplyAccepted(
        reply_id=row.reply_id,
        message_id=payload.message_id,
        received_at=row.received_at,
    )
