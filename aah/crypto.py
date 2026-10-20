"""Optional AES-256-GCM payload envelope (compact token or JSON)."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aah.errors import AppError

COMPACT_PREFIX = "enc:v1:aes-256-gcm:"
JSON_ALG = "AES-256-GCM"


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def looks_encrypted(message: str) -> bool:
    if message.startswith(COMPACT_PREFIX):
        return True
    stripped = message.strip()
    if not stripped.startswith("{"):
        return False
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and parsed.get("enc") == JSON_ALG


def encrypt(key: bytes, plaintext: str, *, associated_data: str) -> str:
    nonce = os.urandom(12)
    aes = AESGCM(key)
    packed = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data.encode("utf-8"))
    ciphertext, tag = packed[:-16], packed[-16:]
    return (
        f"{COMPACT_PREFIX}{b64encode(nonce)}:{b64encode(ciphertext)}:{b64encode(tag)}"
    )


def decrypt(key: bytes, message: str, *, associated_data: str) -> str:
    try:
        nonce, ciphertext, tag = _parse_envelope(message)
        aes = AESGCM(key)
        packed = ciphertext + tag
        plain = aes.decrypt(nonce, packed, associated_data.encode("utf-8"))
        return plain.decode("utf-8")
    except AppError:
        raise
    except (InvalidTag, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AppError(
            400,
            "invalid_ciphertext",
            "Encrypted message could not be decrypted with the configured key.",
        ) from exc


def validate_message_crypto(
    message: str,
    *,
    agent_id: str,
    key: bytes | None,
    require_encryption: bool,
) -> None:
    encrypted = looks_encrypted(message)
    if require_encryption and not encrypted:
        raise AppError(
            400,
            "encryption_required",
            "This server requires AES-256-GCM envelopes for the message field.",
        )
    if not encrypted:
        return
    if key is None:
        raise AppError(
            400,
            "encryption_not_configured",
            "Encrypted payload received but AAH_PAYLOAD_KEY is not configured.",
        )
    decrypt(key, message, associated_data=agent_id)


def _parse_envelope(message: str) -> tuple[bytes, bytes, bytes]:
    if message.startswith(COMPACT_PREFIX):
        rest = message[len(COMPACT_PREFIX) :]
        parts = rest.split(":")
        if len(parts) != 3:
            raise AppError(400, "invalid_ciphertext", "Malformed compact encryption envelope.")
        nonce, ciphertext, tag = (b64decode(part) for part in parts)
        _check_sizes(nonce, tag)
        return nonce, ciphertext, tag

    parsed: dict[str, Any] = json.loads(message)
    if parsed.get("enc") != JSON_ALG:
        raise AppError(400, "invalid_ciphertext", "Unsupported encryption algorithm.")
    nonce = b64decode(str(parsed["iv"]))
    ciphertext = b64decode(str(parsed["ciphertext"]))
    tag = b64decode(str(parsed["tag"]))
    _check_sizes(nonce, tag)
    return nonce, ciphertext, tag


def _check_sizes(nonce: bytes, tag: bytes) -> None:
    if len(nonce) != 12 or len(tag) != 16:
        raise AppError(400, "invalid_ciphertext", "Invalid nonce or authentication tag size.")
