"""Payload envelopes: operator enc:v1 and automatic agent enc:v2 (X25519)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from aah.errors import AppError

COMPACT_PREFIX = "enc:v1:aes-256-gcm:"
V2_PREFIX = "enc:v2:x25519-aes-256-gcm:"
JSON_ALG = "AES-256-GCM"
HKDF_INFO = b"aah-v2"
HKDF_SALT = b""


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def b64decode_flex(value: str) -> bytes:
    raw = value.strip().replace("-", "+").replace("_", "/")
    raw += "=" * ((4 - len(raw) % 4) % 4)
    return base64.b64decode(raw.encode("ascii"))


def looks_v2(message: str) -> bool:
    return message.startswith(V2_PREFIX)


def looks_v1(message: str) -> bool:
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


def looks_encrypted(message: str) -> bool:
    return looks_v2(message) or looks_v1(message)


def generate_x25519_keypair() -> tuple[bytes, bytes]:
    private = X25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    return private.private_bytes_raw(), public


def load_x25519_public(raw: bytes) -> X25519PublicKey:
    if len(raw) != 32:
        raise AppError(400, "invalid_public_key", "X25519 public key must be 32 bytes.")
    try:
        return X25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise AppError(400, "invalid_public_key", "X25519 public key is not valid.") from exc


def decode_public_key(value: str) -> bytes:
    try:
        raw = b64decode_flex(value)
    except Exception as exc:
        raise AppError(400, "invalid_public_key", "public_key must be base64.") from exc
    load_x25519_public(raw)
    return raw


def derive_v2_aes_key(private: X25519PrivateKey, peer_public: bytes) -> bytes:
    shared = private.exchange(load_x25519_public(peer_public))
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=HKDF_SALT,
        info=HKDF_INFO,
    ).derive(shared)


def parse_v2_envelope(message: str) -> tuple[bytes, bytes, bytes, bytes]:
    if not looks_v2(message):
        raise AppError(400, "invalid_ciphertext", "Not an enc:v2 envelope.")
    parts = message[len(V2_PREFIX) :].split(":")
    if len(parts) != 4:
        raise AppError(
            400,
            "invalid_ciphertext",
            "Malformed enc:v2 envelope. Expected eph_pub:nonce:ciphertext:tag.",
        )
    try:
        eph_pub, nonce, ciphertext, tag = (b64decode_flex(part) for part in parts)
    except Exception as exc:
        raise AppError(400, "invalid_ciphertext", "enc:v2 fields must be base64.") from exc
    load_x25519_public(eph_pub)
    if len(nonce) != 12 or len(tag) != 16:
        raise AppError(400, "invalid_ciphertext", "Invalid nonce or authentication tag size.")
    if not ciphertext:
        raise AppError(400, "invalid_ciphertext", "enc:v2 ciphertext must not be empty.")
    return eph_pub, nonce, ciphertext, tag


def seal_v2(*, recipient_public_key: bytes, plaintext: str, sender_agent_id: str) -> str:
    eph_private = X25519PrivateKey.generate()
    eph_pub = eph_private.public_key().public_bytes_raw()
    aes_key = derive_v2_aes_key(eph_private, recipient_public_key)
    nonce = os.urandom(12)
    packed = AESGCM(aes_key).encrypt(
        nonce,
        plaintext.encode("utf-8"),
        sender_agent_id.encode("utf-8"),
    )
    ciphertext, tag = packed[:-16], packed[-16:]
    return (
        f"{V2_PREFIX}{b64encode(eph_pub)}:{b64encode(nonce)}:"
        f"{b64encode(ciphertext)}:{b64encode(tag)}"
    )


def open_v2(*, recipient_private_key: bytes, envelope: str, sender_agent_id: str) -> str:
    if len(recipient_private_key) != 32:
        raise AppError(400, "invalid_private_key", "X25519 private key must be 32 bytes.")
    eph_pub, nonce, ciphertext, tag = parse_v2_envelope(envelope)
    private = X25519PrivateKey.from_private_bytes(recipient_private_key)
    aes_key = derive_v2_aes_key(private, eph_pub)
    try:
        plain = AESGCM(aes_key).decrypt(
            nonce,
            ciphertext + tag,
            sender_agent_id.encode("utf-8"),
        )
        return plain.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError) as exc:
        raise AppError(
            400,
            "invalid_ciphertext",
            "enc:v2 message could not be opened with the recipient private key.",
        ) from exc


def encrypt(key: bytes, plaintext: str, *, associated_data: str) -> str:
    nonce = os.urandom(12)
    aes = AESGCM(key)
    packed = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data.encode("utf-8"))
    ciphertext, tag = packed[:-16], packed[-16:]
    return f"{COMPACT_PREFIX}{b64encode(nonce)}:{b64encode(ciphertext)}:{b64encode(tag)}"


def decrypt(key: bytes, message: str, *, associated_data: str) -> str:
    try:
        nonce, ciphertext, tag = _parse_v1_envelope(message)
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
    to_agent_id: str | None = None,
    peer_key_exists: bool | None = None,
) -> None:
    if looks_v2(message):
        parse_v2_envelope(message)
        if to_agent_id and peer_key_exists is False:
            raise AppError(
                400,
                "peer_key_missing",
                "enc:v2 requires a published X25519 public key for payload.to_agent_id.",
            )
        return
    if looks_v1(message):
        if key is None:
            raise AppError(
                400,
                "encryption_not_configured",
                "enc:v1 payload received but AAH_PAYLOAD_KEY is not configured.",
            )
        decrypt(key, message, associated_data=agent_id)
        return
    bootstrap = bool(to_agent_id) and peer_key_exists is False
    if require_encryption and not bootstrap:
        raise AppError(
            400,
            "encryption_required",
            "This server requires an enc:v2 (or operator enc:v1) envelope.",
        )


def _parse_v1_envelope(message: str) -> tuple[bytes, bytes, bytes]:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m aah.crypto",
        description="Local helpers for automatic X25519 enc:v2. Private keys never go to the hub.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Create a long-term X25519 keypair")
    gen.add_argument("--agent-id", default="")

    reg = sub.add_parser("register-payload", help="Print PUT /api/v1/keys JSON body")
    reg.add_argument("--agent-id", required=True)
    reg.add_argument("--public-key")
    reg.add_argument("--private-key")

    seal = sub.add_parser("seal", help="Seal plaintext to a peer public key")
    seal.add_argument("--to-public-key", required=True)
    seal.add_argument("--from-agent-id", required=True)
    seal.add_argument("--message", required=True)

    opener = sub.add_parser("open", help="Open an enc:v2 envelope with your private key")
    opener.add_argument("--private-key", required=True)
    opener.add_argument("--envelope", required=True)
    opener.add_argument("--from-agent-id", required=True)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "generate":
            private, public = generate_x25519_keypair()
            payload = {
                "private_key": b64encode(private),
                "public_key": b64encode(public),
            }
            if args.agent_id:
                payload["agent_id"] = args.agent_id
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        if args.cmd == "register-payload":
            if args.public_key:
                public = decode_public_key(args.public_key)
            elif args.private_key:
                raw = b64decode_flex(args.private_key)
                public = X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()
            else:
                private, public = generate_x25519_keypair()
                json.dump(
                    {
                        "agent_id": args.agent_id,
                        "public_key": b64encode(public),
                        "private_key": b64encode(private),
                    },
                    sys.stdout,
                    indent=2,
                )
                sys.stdout.write("\n")
                return 0
            json.dump(
                {"agent_id": args.agent_id, "public_key": b64encode(public)},
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0
        if args.cmd == "seal":
            envelope = seal_v2(
                recipient_public_key=decode_public_key(args.to_public_key),
                plaintext=args.message,
                sender_agent_id=args.from_agent_id,
            )
            sys.stdout.write(envelope + "\n")
            return 0
        if args.cmd == "open":
            plain = open_v2(
                recipient_private_key=b64decode_flex(args.private_key),
                envelope=args.envelope,
                sender_agent_id=args.from_agent_id,
            )
            sys.stdout.write(plain + "\n")
            return 0
    except AppError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
