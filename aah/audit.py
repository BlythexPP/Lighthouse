"""Structured JSON audit logging. Never records secrets or payload bodies."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

WEBHOOK_URL_RE = re.compile(
    r"https?://(?:(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services)/\S+",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    return WEBHOOK_URL_RE.sub("https://[redacted]", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        audit = getattr(record, "audit", None)
        if isinstance(audit, dict):
            payload["audit"] = {
                key: redact_secrets(value) if isinstance(value, str) else value
                for key, value in audit.items()
            }
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def emit(event: str, **fields: Any) -> None:
    logging.getLogger("aah.audit").info(
        event,
        extra={"audit": {"event": event, **fields}},
    )
