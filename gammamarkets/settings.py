"""Extension-owned ``GAMMAMARKETS_*`` configuration (spec section 12).

The host has no extension-settings hook, so this module parses and strictly
validates its own environment. Validation failure raises before merchant
services activate: ``gammamarkets_start`` propagates it and the host marks
the extension inactive.

Keyring format::

    GAMMAMARKETS_MASTER_KEYS={"v1":"<base64 32 bytes>","v2":"..."}
    GAMMAMARKETS_ACTIVE_KEY_VERSION=v2
    GAMMAMARKETS_PRIVACY_KEY=<base64 or 64-hex 32 bytes>
    GAMMAMARKETS_PUBLIC_BASE_URL=https://shop.example
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


class SettingsError(RuntimeError):
    """A required GAMMAMARKETS_* setting is missing or malformed."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SettingsError(f"{name} is required")
    return value


def _decode_32(name: str, value: str) -> bytes:
    """Strictly decode a 32-byte secret (base64 or 64-hex)."""
    raw: bytes | None = None
    try:
        candidate = base64.b64decode(value, validate=True)
        if len(candidate) == 32:
            raw = candidate
    except (binascii.Error, ValueError):
        pass
    if raw is None and len(value) == 64:
        try:
            candidate = bytes.fromhex(value)
            if len(candidate) == 32:
                raw = candidate
        except ValueError:
            pass
    if raw is None:
        raise SettingsError(f"{name} must decode to exactly 32 bytes")
    return raw


def _parse_keyring(raw: str) -> dict[str, bytes]:
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError(
            "GAMMAMARKETS_MASTER_KEYS must be a JSON object of "
            '{"version": "<base64 32-byte key>"}'
        ) from exc
    if not isinstance(mapping, dict) or not mapping:
        raise SettingsError("GAMMAMARKETS_MASTER_KEYS must be a non-empty map")
    keyring: dict[str, bytes] = {}
    for version, encoded in mapping.items():
        if not isinstance(version, str) or not version:
            raise SettingsError("GAMMAMARKETS_MASTER_KEYS versions must be non-empty strings")
        if not isinstance(encoded, str):
            raise SettingsError(
                f"GAMMAMARKETS_MASTER_KEYS[{version!r}] must be a base64 string"
            )
        try:
            key = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SettingsError(
                f"GAMMAMARKETS_MASTER_KEYS[{version!r}] is not valid base64"
            ) from exc
        if len(key) != 32:
            raise SettingsError(
                f"GAMMAMARKETS_MASTER_KEYS[{version!r}] must decode to 32 bytes"
            )
        keyring[version] = key
    # Duplicate key material under two versions breaks rotation semantics.
    if len(set(keyring.values())) != len(keyring):
        raise SettingsError("GAMMAMARKETS_MASTER_KEYS contains duplicate key material")
    return keyring


def _parse_base_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SettingsError(
            "GAMMAMARKETS_PUBLIC_BASE_URL must be an https:// origin "
            "(never derived from Host/Forwarded headers)"
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SettingsError(
            "GAMMAMARKETS_PUBLIC_BASE_URL must not carry userinfo, query, or fragment"
        )
    if parsed.path not in ("", "/"):
        raise SettingsError(
            "GAMMAMARKETS_PUBLIC_BASE_URL must be an origin (no path)"
        )
    return f"https://{parsed.netloc}"


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer") from exc
    if value < minimum:
        raise SettingsError(f"{name} must be >= {minimum}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(f"{name} must be a boolean")


@dataclass(frozen=True)
class ExtSettings:
    master_keys: dict[str, bytes]
    active_key_version: str
    privacy_key: bytes
    public_base_url: str
    reservation_ttl: int = 900
    outbox_max_attempts: int = 20
    outbox_batch: int = 32
    peer_relay_ttl: int = 86400
    inbox_max_event_bytes: int = 32768
    checkout_rate_limit: int = 10  # per minute per IP (section 15)
    checkout_rate_limit_hourly: int = 100  # per hour per IP (section 15)
    email_enabled: bool = True
    email_max_attempts: int = 5
    spec_revision: str = "5dc79c5"
    extra: dict = field(default_factory=dict)


def ext_settings() -> ExtSettings:
    """Parse + strictly validate the extension environment (section 12)."""
    keyring = _parse_keyring(_require("GAMMAMARKETS_MASTER_KEYS"))
    active = _require("GAMMAMARKETS_ACTIVE_KEY_VERSION")
    if active not in keyring:
        raise SettingsError(
            "GAMMAMARKETS_ACTIVE_KEY_VERSION must name a key present in "
            "GAMMAMARKETS_MASTER_KEYS"
        )
    privacy = _decode_32(
        "GAMMAMARKETS_PRIVACY_KEY", _require("GAMMAMARKETS_PRIVACY_KEY")
    )
    if privacy in keyring.values():
        raise SettingsError(
            "GAMMAMARKETS_PRIVACY_KEY must be distinct from master keys"
        )
    base_url = _parse_base_url(_require("GAMMAMARKETS_PUBLIC_BASE_URL"))
    return ExtSettings(
        master_keys=keyring,
        active_key_version=active,
        privacy_key=privacy,
        public_base_url=base_url,
        reservation_ttl=_int_env("GAMMAMARKETS_RESERVATION_TTL", 900),
        outbox_max_attempts=_int_env("GAMMAMARKETS_OUTBOX_MAX_ATTEMPTS", 20),
        outbox_batch=_int_env("GAMMAMARKETS_OUTBOX_BATCH", 32),
        peer_relay_ttl=_int_env("GAMMAMARKETS_PEER_RELAY_TTL", 86400),
        inbox_max_event_bytes=_int_env("GAMMAMARKETS_INBOX_MAX_EVENT_BYTES", 32768),
        checkout_rate_limit=_int_env("GAMMAMARKETS_CHECKOUT_RATE_LIMIT", 10),
        checkout_rate_limit_hourly=_int_env(
            "GAMMAMARKETS_CHECKOUT_RATE_LIMIT_HOURLY", 100
        ),
        email_enabled=_bool_env("GAMMAMARKETS_EMAIL_ENABLED", True),
        email_max_attempts=_int_env("GAMMAMARKETS_EMAIL_MAX_ATTEMPTS", 5),
        spec_revision=os.environ.get(
            "GAMMAMARKETS_SPEC_REVISION", "5dc79c5"
        ).strip()
        or "5dc79c5",
    )
