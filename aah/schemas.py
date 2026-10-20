"""Pydantic request/response models used for runtime validation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from aah.util import utc_z

MessageType = Literal["text", "event", "status"]


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=0, max_length=200_000)
    reply_channel: str | None = Field(default=None, max_length=128)

    @field_validator("reply_channel", mode="before")
    @classmethod
    def empty_channel_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator("reply_channel")
    @classmethod
    def channel_charset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")
        if not set(value) <= allowed:
            raise ValueError("reply_channel contains unsupported characters")
        return value


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    timestamp: AwareDatetime
    message_type: MessageType
    payload: MessagePayload


class MessageAccepted(BaseModel):
    status: Literal["received"]
    message_id: str
    relay_status: str


class EgressReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(pattern=r"^msg_[0-9a-f]{32}$")
    source: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    content: str = Field(min_length=0, max_length=200_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_small_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, default=str)
        if len(encoded) > 16_384:
            raise ValueError("metadata exceeds 16KiB")
        return value


class EgressReplyAccepted(BaseModel):
    reply_id: str
    message_id: str
    received_at: str


class EgressReplyView(BaseModel):
    reply_id: str
    source: str
    content: str
    metadata: dict[str, Any]
    received_at: str


class MessageView(BaseModel):
    message_id: str
    agent_id: str
    timestamp: str
    received_at: str
    message_type: str
    payload: MessagePayload
    status: Literal["received"]
    relay_status: str
    replies: list[EgressReplyView]


class ResponsesView(BaseModel):
    responses: list[MessageView]


def serialize_timestamp(value: datetime) -> str:
    return utc_z(value)
