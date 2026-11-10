"""Open X25519 public-key directory. Private keys never touch this service."""

from __future__ import annotations

from fastapi import APIRouter, Request

from aah.audit import emit
from aah.auth import optional_agent_name
from aah.errors import AppError
from aah.ratelimit import RateLimiter
from aah.schemas import KeyPublishRequest, KeyView
from aah.store import Store

router = APIRouter()


@router.put("/api/v1/keys", response_model=KeyView)
async def put_key(payload: KeyPublishRequest, request: Request) -> KeyView:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check_request(request)
    store: Store = request.app.state.store
    row, created = await store.upsert_key(
        agent_id=payload.agent_id,
        public_key=payload.public_key,
    )
    emit(
        "key_published",
        caller=optional_agent_name(request),
        agent_id=row.agent_id,
        created=created,
    )
    return KeyView(
        agent_id=row.agent_id,
        public_key=row.public_key,
        updated_at=row.updated_at,
    )


@router.get("/api/v1/keys/{agent_id}", response_model=KeyView)
async def get_key(agent_id: str, request: Request) -> KeyView:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check_request(request)
    store: Store = request.app.state.store
    row = await store.get_key(agent_id)
    if row is None:
        raise AppError(404, "not_found", "Unknown agent_id.")
    emit("key_read", caller=optional_agent_name(request), agent_id=agent_id)
    return KeyView(agent_id=row.agent_id, public_key=row.public_key, updated_at=row.updated_at)
