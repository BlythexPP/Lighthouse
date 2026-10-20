"""Async SQLAlchemy models and engine lifecycle."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("client_id", "idempotency_key", name="uq_message_idempotency"),
    )

    message_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128))
    agent_timestamp: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[str] = mapped_column(String(64), index=True)
    message_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    reply_channel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relay_status: Mapped[str] = mapped_column(String(32))
    delivery_attempts: Mapped[int] = mapped_column(Integer)
    last_delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    replies: Mapped[list[ReplyRow]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class ReplyRow(Base):
    __tablename__ = "replies"

    reply_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)
    received_at: Mapped[str] = mapped_column(String(64))

    message: Mapped[MessageRow] = relationship(back_populates="replies")


class AgentKeyRow(Base):
    __tablename__ = "agent_keys"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    public_key: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[str] = mapped_column(String(64))


def sqlite_path_from_url(database_url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return None
    rest = database_url[len(prefix) :]
    if rest in {":memory:", "/:memory:"}:
        return None
    return Path(rest)


def create_engine(database_url: str) -> AsyncEngine:
    path = sqlite_path_from_url(database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        if database_url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


async def init_db(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def ping_db(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(select(1))
