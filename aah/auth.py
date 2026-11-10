"""Optional caller label from X-Agent-Identifier. This is a name, not authentication."""

from __future__ import annotations

from fastapi import Request

from aah.contract import AGENT_NAME_HEADER

ANONYMOUS = "anonymous"


def optional_agent_name(request: Request) -> str:
    value = (request.headers.get(AGENT_NAME_HEADER) or "").strip()
    if not value:
        return ANONYMOUS
    return value[:128]
