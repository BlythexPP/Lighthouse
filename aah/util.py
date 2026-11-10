"""Small shared helpers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_z(value: datetime | None = None) -> str:
    stamp = (value or utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    return stamp.isoformat().replace("+00:00", "Z")


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex}"


def new_reply_id() -> str:
    return f"rpl_{uuid.uuid4().hex}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit < 4:
        return value[:limit]
    return value[: limit - 3] + "..."


def sanitize_error(text: str, secret_fragments: list[str]) -> str:
    cleaned = text
    for fragment in secret_fragments:
        if fragment:
            cleaned = cleaned.replace(fragment, "[redacted]")
    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        cleaned = f"{parsed.scheme}://[redacted]{parsed.path[:24]}"
    return cleaned[:512]


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"
