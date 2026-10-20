"""Persistence helpers for messages and channel replies."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from aah.db import MessageRow, ReplyRow
from aah.errors import AppError
from aah.util import new_message_id, new_reply_id, utc_z

LIST_LIMIT = 100


class Store:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create_message(
        self,
        *,
        client_id: str,
        agent_id: str,
        agent_timestamp: str,
        message_type: str,
        content: str,
        reply_channel: str | None,
        idempotency_key: str | None,
        request_hash: str,
    ) -> tuple[MessageRow, bool]:
        """Insert a message. Returns (row, created). created is False on idempotent replay."""
        if idempotency_key:
            existing = await self.get_by_idempotency(client_id, idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise AppError(
                        409,
                        "idempotency_conflict",
                        "Idempotency-Key was reused with a different request body.",
                    )
                return existing, False

        row = MessageRow(
            message_id=new_message_id(),
            client_id=client_id,
            agent_id=agent_id,
            agent_timestamp=agent_timestamp,
            received_at=utc_z(),
            message_type=message_type,
            content=content,
            reply_channel=reply_channel,
            relay_status="accepted",
            delivery_attempts=0,
            last_delivery_error=None,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        async with self._sessions() as session:
            session.add(row)
            try:
                await session.commit()
                await session.refresh(row)
            except IntegrityError as exc:
                await session.rollback()
                if not idempotency_key:
                    raise AppError(500, "persist_failed", "Could not persist message.") from exc
                existing = await self.get_by_idempotency(client_id, idempotency_key)
                if existing is None:
                    raise AppError(500, "persist_failed", "Could not persist message.") from exc
                if existing.request_hash != request_hash:
                    raise AppError(
                        409,
                        "idempotency_conflict",
                        "Idempotency-Key was reused with a different request body.",
                    ) from exc
                return existing, False
            return row, True

    async def get_by_idempotency(self, client_id: str, key: str) -> MessageRow | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(MessageRow).where(
                    MessageRow.client_id == client_id,
                    MessageRow.idempotency_key == key,
                )
            )
            return result.scalar_one_or_none()

    async def get_message(self, message_id: str) -> MessageRow | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(MessageRow)
                .options(selectinload(MessageRow.replies))
                .where(MessageRow.message_id == message_id)
            )
            return result.scalar_one_or_none()

    async def list_messages(self, *, limit: int = LIST_LIMIT) -> list[MessageRow]:
        async with self._sessions() as session:
            stmt = (
                select(MessageRow)
                .options(selectinload(MessageRow.replies))
                .order_by(MessageRow.received_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().unique().all())

    async def update_delivery(
        self,
        message_id: str,
        *,
        status: str,
        attempts: int,
        error: str | None,
    ) -> None:
        async with self._sessions() as session:
            row = await session.get(MessageRow, message_id)
            if row is None:
                return
            row.relay_status = status
            row.delivery_attempts = attempts
            row.last_delivery_error = error
            await session.commit()

    async def add_reply(
        self,
        *,
        message_id: str,
        source: str,
        content: str,
        metadata: dict[str, Any],
    ) -> ReplyRow:
        row = ReplyRow(
            reply_id=new_reply_id(),
            message_id=message_id,
            source=source,
            content=content,
            metadata_json=json.dumps(metadata, ensure_ascii=False, default=str),
            received_at=utc_z(),
        )
        async with self._sessions() as session:
            message = await session.get(MessageRow, message_id)
            if message is None:
                raise AppError(404, "not_found", "Unknown message_id.")
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row
