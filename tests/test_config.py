from __future__ import annotations

import pytest
from pydantic import SecretStr

from aah.config import ConfigError, Settings


def test_starts_without_agent_credentials():
    Settings().validate_runtime()


def test_webhook_must_be_https_when_required():
    with pytest.raises(ConfigError, match="https"):
        Settings(
            webhook_url="http://example.test/hook",
            webhook_require_tls=True,
        ).validate_runtime()


def test_invalid_payload_key():
    with pytest.raises(ConfigError):
        Settings(payload_key=SecretStr("not-base64")).validate_runtime()
