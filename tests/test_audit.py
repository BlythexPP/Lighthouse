from __future__ import annotations

import json
import logging

from aah.audit import JsonFormatter, setup_logging


def test_json_formatter_redacts_discord_webhook_urls():
    setup_logging("INFO")
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "HTTP Request: POST https://discord.com/api/webhooks/1/super-secret-token "
            '"HTTP/1.1 204 No Content"'
        ),
        args=(),
        exc_info=None,
    )
    rendered = JsonFormatter().format(record)
    body = json.loads(rendered)
    assert "super-secret-token" not in rendered
    assert "discord.com/api/webhooks/1" not in rendered
    assert body["message"] == 'HTTP Request: POST https://[redacted] "HTTP/1.1 204 No Content"'
    assert logging.getLogger("httpx").level == logging.WARNING
