"""Minimal nostr-sdk helpers for the qualification probes.

SDK-only — no custom cryptography (STACK.md non-selection). The verified
0.44.8 API surface used here:

- ``Keys.generate()`` / ``Keys.secret_key()`` / ``Keys.public_key()``
- ``EventBuilder.text_note(content).sign(NostrSigner.keys(keys))`` (async)
- ``Event.verify()`` / ``Event.verify_id()`` / ``Event.verify_signature()``
  — boolean returns; ``Event.from_json``/``as_json`` for tamper construction
- ``nip44_encrypt(secret_key, pubkey, plaintext, Nip44Version.V2)`` /
  ``nip44_decrypt(secret_key, pubkey, ciphertext)`` — the ``version``
  argument is REQUIRED positional in this build.
"""

from __future__ import annotations

import json

from nostr_sdk import (
    Event,
    EventBuilder,
    Keys,
    Nip44Version,
    NostrSigner,
    nip44_decrypt,
    nip44_encrypt,
)


def generate_keys() -> Keys:
    """Generate a fresh keypair (synthetic test keys only — T-01-03)."""
    return Keys.generate()


async def sign_text_note(keys: Keys, content: str) -> Event:
    """Build and sign a kind-1 event."""
    return await EventBuilder.text_note(content).sign(NostrSigner.keys(keys))


def verify_event(event: Event) -> bool:
    """Full SDK verification (id + signature)."""
    return event.verify()


def tamper_event(event: Event, **changes: str) -> Event:
    """Rebuild an event with tampered fields via its JSON form.

    The id/signature stay as originally computed, so any tampered field must
    make verification fail (id mismatch for content tampering, signature
    mismatch for sig tampering).
    """
    data = json.loads(event.as_json())
    for key, value in changes.items():
        data[key] = value
    return Event.from_json(json.dumps(data))


def nip44_roundtrip(sender: Keys, recipient: Keys, plaintext: str) -> str:
    """NIP-44 v2 encrypt (sender -> recipient) then decrypt (recipient)."""
    ciphertext = nip44_encrypt(
        sender.secret_key(), recipient.public_key(), plaintext, Nip44Version.V2
    )
    return nip44_decrypt(
        recipient.secret_key(), sender.public_key(), ciphertext
    )


def event_id(event: Event) -> str:
    """The event id as hex."""
    return event.id().to_hex()


class IdRegistry:
    """Admission-modeled exactly-once event-id dedupe.

    D-16 disclosure: this is EXTENSION-SIDE defense in depth only. It models
    the admission layer the production extension must implement; it cannot
    waive an SDK-internal dedupe or verification regression, which remains
    blocking under D-13/D-16.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def admit(self, eid: str) -> bool:
        """Return True exactly once per distinct id (True = newly admitted)."""
        if eid in self._seen:
            return False
        self._seen.add(eid)
        return True

    def __len__(self) -> int:
        return len(self._seen)
