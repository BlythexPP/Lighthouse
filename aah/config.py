"""Environment-driven configuration. Operator secrets never have defaults."""

from __future__ import annotations

from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aah.contract import SERVICE_NAME


class ConfigError(Exception):
    """Raised when the process cannot start with the current environment."""


def _empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, SecretStr) and not value.get_secret_value().strip():
        return None
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AAH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./data/aah.db"
    public_base_url: str = "http://127.0.0.1:8080"
    enable_docs: bool = True

    webhook_url: SecretStr | None = None
    webhook_require_tls: bool = True
    webhook_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    webhook_max_retries: int = Field(default=3, ge=0, le=10)
    webhook_retry_backoff_seconds: float = Field(default=0.2, ge=0, le=10)

    payload_key: SecretStr | None = None
    require_encryption: bool = False

    rate_limit_per_minute: int = Field(default=120, ge=0)
    max_body_bytes: int = Field(default=262144, ge=1024, le=8_388_608)

    service_name: str = SERVICE_NAME

    @field_validator(
        "webhook_url",
        "payload_key",
        mode="before",
    )
    @classmethod
    def empty_optional(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @field_validator("public_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    def payload_key_bytes(self) -> bytes | None:
        if self.payload_key is None:
            return None
        import base64

        raw = self.payload_key.get_secret_value().strip()
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise ConfigError("AAH_PAYLOAD_KEY must be standard base64.") from exc
        if len(key) != 32:
            raise ConfigError("AAH_PAYLOAD_KEY must decode to exactly 32 bytes.")
        return key

    def webhook_url_value(self) -> str | None:
        if self.webhook_url is None:
            return None
        return self.webhook_url.get_secret_value().strip() or None

    def validate_runtime(self) -> None:
        self.payload_key_bytes()
        url = self.webhook_url_value()
        if url:
            if self.webhook_require_tls and not url.lower().startswith("https://"):
                raise ConfigError("AAH_WEBHOOK_URL must use https when TLS is required.")
            if not (url.lower().startswith("https://") or url.lower().startswith("http://")):
                raise ConfigError("AAH_WEBHOOK_URL must be an absolute http(s) URL.")
        if self.require_encryption and self.payload_key_bytes() is None:
            raise ConfigError("AAH_REQUIRE_ENCRYPTION=true needs AAH_PAYLOAD_KEY.")


def load_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
