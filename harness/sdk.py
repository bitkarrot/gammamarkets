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

import hashlib
import json
import logging

from nostr_sdk import (
    Event,
    EventBuilder,
    Keys,
    Kind,
    Nip44Version,
    NostrSigner,
    PublicKey,
    Tag,
    Timestamp,
    UnsignedEvent,
    gift_wrap_from_seal,
    nip44_decrypt,
    nip44_encrypt,
)

logger = logging.getLogger(__name__)


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


# --- NIP-59 / NIP-17 gift-wrap construction and verification (sections 6.9, 8.5)
#
# Verified against nostr-sdk 0.44.8 (instance-level introspection — pyo3 hides
# fields from class-level dir()):
#
# - ``EventBuilder(Kind(n), content).tags([...]).build(pubkey)`` produces an
#   UNSIGNED rumor (no ``sig`` in its JSON); ``custom_created_at`` pins the
#   rumor timestamp (rumor ``created_at`` is real time per section 6.9).
# - ``EventBuilder.seal(signer, receiver_pubkey, rumor)`` is async and returns
#   an EventBuilder (kind 13, empty tags); ``.sign(signer)`` produces the
#   signed seal with a NIP-59-randomized past timestamp.
# - ``gift_wrap_from_seal(receiver_pubkey, seal)`` is SYNC (not a coroutine)
#   and returns the kind-1059 wrap signed by a fresh ephemeral key with its
#   own randomized past timestamp; the wrap carries exactly one ``p`` tag.
# - ``UnwrappedGift.from_gift_wrap(signer, wrap)`` is the SDK composite unwrap;
#   the explicit chain below re-implements the same steps stage by stage so
#   the tamper matrix can pinpoint WHICH stage rejects.
# - ``UnsignedEvent.id()`` returns the STORED id field (it does not recompute
#   the hash), so the canonical NIP-01 id check below rebuilds the event
#   through the SDK builder and compares — no custom hash code.

KIND_SEAL = 13
KIND_GIFT_WRAP = 1059
KIND_ORDER_MESSAGE = 16
KIND_RECEIPT = 17
KIND_DM = 14

#: Rumor kinds the inbox may dispatch (section 8.5 step 8).
ALLOWED_RUMOR_KINDS = frozenset({KIND_DM, KIND_ORDER_MESSAGE, KIND_RECEIPT})

#: NIP-59 backdating bound: seal/wrap timestamps are randomized up to two
#: days in the past (section 6.9).
NIP59_MAX_SKEW_S = 2 * 24 * 3600


class WrapRejection(Exception):
    """A gift-wrap chain failed validation before trusted processing.

    The message is a BOUNDED reason code — it never carries ciphertext,
    plaintext, or key material (section 8.5 quarantine discipline, PITFALLS
    NIP-17 privacy leak).
    """


def fixed_test_keys(label: str) -> Keys:
    """A deterministic synthetic keypair for golden fixtures (T-01-03).

    The secret is ``sha256("gammamarkets-qual:" + label)`` — a fixed test
    value, never a real key.
    """
    secret_hex = hashlib.sha256(f"gammamarkets-qual:{label}".encode()).hexdigest()
    return Keys.parse(secret_hex)


def build_order_rumor(
    author: Keys,
    recipient_pubkey: PublicKey,
    *,
    order_external_id: str,
    amount_sat: int,
    items: list[tuple[str, int]],
    created_at: int,
    content: str = "",
    extra_tags: list[list[str]] | None = None,
) -> UnsignedEvent:
    """A kind-16 type-1 order rumor (section 6.9), unsigned.

    Common tags: exactly one ``p`` (recipient), one ``subject``, one ``type``,
    one ``order``; plus ``amount`` and one ``item`` tag per line.
    ``created_at`` is pinned by the caller (real time at construction; retries
    reuse the identical rumor so the canonical id stays stable, section 8.6).
    """
    tags = [
        Tag.parse(["p", recipient_pubkey.to_hex()]),
        Tag.parse(["subject", "order"]),
        Tag.parse(["type", "1"]),
        Tag.parse(["order", order_external_id]),
        Tag.parse(["amount", str(amount_sat)]),
    ]
    for address, qty in items:
        tags.append(Tag.parse(["item", address, str(qty)]))
    for tag in extra_tags or []:
        tags.append(Tag.parse(tag))
    return (
        EventBuilder(Kind(KIND_ORDER_MESSAGE), content)
        .custom_created_at(Timestamp.from_secs(created_at))
        .tags(tags)
        .build(author.public_key())
    )


async def seal_rumor(sender: Keys, recipient_pubkey: PublicKey, rumor: UnsignedEvent) -> Event:
    """Seal a rumor (kind 13, empty tags) signed by the sender.

    The seal timestamp is randomized up to two days in the past by the SDK
    (NIP-59). The seal author is the rumor author — the outer wrap key is
    never identity (section 8.5 step 6).
    """
    builder = await EventBuilder.seal(
        NostrSigner.keys(sender), recipient_pubkey, rumor
    )
    return await builder.sign(NostrSigner.keys(sender))


def wrap_seal(recipient_pubkey: PublicKey, seal: Event) -> Event:
    """Gift-wrap a signed seal with a fresh ephemeral wrapper key.

    ``gift_wrap_from_seal`` is SYNCHRONOUS in 0.44.8; it generates the
    one-time outer key and the randomized past timestamp itself.
    """
    return gift_wrap_from_seal(recipient_pubkey, seal)


async def wrap_order_copy(
    sender: Keys, recipient_pubkey: PublicKey, rumor: UnsignedEvent
) -> tuple[Event, Event]:
    """One NIP-17 delivery copy: (seal, wrap) for ``recipient_pubkey``.

    Every copy is independently sealed and wrapped with a fresh ephemeral
    wrapper key (section 6.9 two-copy rule). ``rumor`` is reused verbatim so
    the canonical rumor id is stable across copies and retries.
    """
    seal = await seal_rumor(sender, recipient_pubkey, rumor)
    return seal, wrap_seal(recipient_pubkey, seal)


def canonical_rumor_id(rumor: UnsignedEvent) -> str:
    """The canonical NIP-01 id of a rumor, recomputed through the SDK.

    ``UnsignedEvent.id()`` returns the stored field — it does NOT recompute
    the hash — so the canonical id is derived by rebuilding the event with
    the same (pubkey, created_at, kind, tags, content) through the SDK
    builder, which computes the hash honestly.
    """
    rebuilt = (
        EventBuilder(rumor.kind(), rumor.content())
        .custom_created_at(rumor.created_at())
        .tags([Tag.parse(tag.as_vec()) for tag in rumor.tags().to_vec()])
        .build(rumor.author())
    )
    return rebuilt.id().to_hex()


def _reject(reason: str) -> None:
    logger.info("gift-wrap rejected: %s", reason)  # ids/reasons only, never content
    raise WrapRejection(reason)


def _single_tag_values(event_tags, name: str) -> list[str]:
    return [tag.as_vec()[1] for tag in event_tags.to_vec()
            if tag.as_vec() and tag.as_vec()[0] == name and len(tag.as_vec()) >= 2]


async def unwrap_gift_wrap(
    recipient: Keys,
    wrap: Event,
    expected_rumor_recipient: PublicKey | None = None,
) -> tuple[Event, UnsignedEvent]:
    """The explicit section 8.5 verification chain for one kind-1059 wrap.

    Returns ``(seal, rumor)`` on success; raises ``WrapRejection`` with a
    bounded reason at the FIRST failing stage. Stages, in order:

    1. kind must be 1059 and the outer id/signature must verify;
    2. exactly one ``p`` tag, equal to the recipient (target) pubkey — the
       wrap is always addressed to whoever unwraps it, sender copy included;
    3. NIP-44-decrypt outer content (recipient key x outer ephemeral pubkey)
       -> seal JSON;
    4. seal parses, is kind 13 with empty tags, and verifies (id+signature);
    5. NIP-44-decrypt seal content (recipient key x seal pubkey) -> rumor;
    6. rumor parses as an unsigned event whose stored id equals the canonical
       NIP-01 hash and whose pubkey equals the seal's pubkey;
    7. rumor kind is in {14, 16, 17} with exactly one ``p`` tag equal to the
       *message* recipient.

    The rumor ``p`` tag names the message's recipient. For a sender copy the
    wrap recipient is the sender but the message recipient is still the
    buyer, so pass ``expected_rumor_recipient`` (the buyer's pubkey) when
    validating a sender copy; it defaults to ``recipient.public_key()``.
    """
    if expected_rumor_recipient is None:
        expected_rumor_recipient = recipient.public_key()
    if wrap.kind().as_u16() != KIND_GIFT_WRAP:
        _reject("outer-kind-not-1059")
    if not wrap.verify():
        _reject("outer-id-or-signature-invalid")

    p_values = _single_tag_values(wrap.tags(), "p")
    if len(p_values) != 1:
        _reject("outer-p-tag-count")
    if p_values[0] != recipient.public_key().to_hex():
        _reject("outer-p-tag-not-recipient")

    try:
        seal_json = nip44_decrypt(
            recipient.secret_key(), wrap.author(), wrap.content()
        )
    except Exception:  # noqa: BLE001 — any decrypt failure is a clean reject
        _reject("outer-decrypt-failed")
    try:
        seal = Event.from_json(seal_json)
    except Exception:  # noqa: BLE001
        _reject("seal-unparseable")

    if seal.kind().as_u16() != KIND_SEAL:
        _reject("seal-kind-not-13")
    if not seal.tags().is_empty():
        _reject("seal-tags-not-empty")
    if not seal.verify():
        _reject("seal-id-or-signature-invalid")

    try:
        rumor_json = nip44_decrypt(
            recipient.secret_key(), seal.author(), seal.content()
        )
    except Exception:  # noqa: BLE001
        _reject("seal-decrypt-failed")

    rumor_data: dict
    try:
        rumor_data = json.loads(rumor_json)
    except (TypeError, ValueError):
        _reject("rumor-unparseable")
    if not isinstance(rumor_data, dict):
        _reject("rumor-unparseable")
    if rumor_data.get("sig"):
        _reject("rumor-signed")
    try:
        rumor = UnsignedEvent.from_json(rumor_json)
    except Exception:  # noqa: BLE001
        _reject("rumor-unparseable")

    if rumor.id().to_hex() != canonical_rumor_id(rumor):
        _reject("rumor-id-not-canonical")
    if rumor.author().to_hex() != seal.author().to_hex():
        _reject("rumor-seal-pubkey-mismatch")
    if rumor.kind().as_u16() not in ALLOWED_RUMOR_KINDS:
        _reject("rumor-kind-not-allowed")

    # Tag-count checks run on the RAW JSON tag list: the SDK parser dedupes
    # duplicate tags, so a parsed-level check could never see a duplicate
    # (section 6.9 rejects duplicated common tags).
    raw_tags = rumor_data.get("tags")
    if not isinstance(raw_tags, list):
        _reject("rumor-unparseable")
    raw_names = [t[0] for t in raw_tags if isinstance(t, list) and t]
    for name in ("subject", "type", "order"):
        if raw_names.count(name) > 1:
            _reject("rumor-duplicate-common-tag")
    raw_p = [
        t[1]
        for t in raw_tags
        if isinstance(t, list) and len(t) >= 2 and t[0] == "p"
    ]
    if len(raw_p) != 1 or raw_p[0] != expected_rumor_recipient.to_hex():
        _reject("rumor-p-tag-invalid")

    logger.info(
        "gift-wrap accepted: rumor_id=%s kind=%s",
        rumor.id().to_hex(),
        rumor.kind().as_u16(),
    )
    return seal, rumor


def validate_kind16_tags(rumor_data: dict) -> None:
    """Section 6.9 common-tag validation for a kind-16 rumor JSON dict.

    Exactly one each of ``p``, ``subject``, ``type``, ``order``; a duplicate
    of any common tag is rejected. Runs on the RAW tag list — the SDK parser
    dedupes duplicates, so parsed-level checks cannot see them.
    Raises ``WrapRejection``.
    """
    if rumor_data.get("kind") != KIND_ORDER_MESSAGE:
        _reject("rumor-kind-not-16")
    raw_tags = rumor_data.get("tags")
    if not isinstance(raw_tags, list):
        _reject("rumor-unparseable")
    names = [t[0] for t in raw_tags if isinstance(t, list) and t]
    for name in ("p", "subject", "type", "order"):
        if names.count(name) != 1:
            _reject(f"kind16-{name}-tag-count")


def rumor_from_json(data: dict) -> UnsignedEvent:
    """Parse an unsigned rumor from its JSON dict form."""
    if data.get("sig"):
        raise WrapRejection("rumor-signed")
    return UnsignedEvent.from_json(json.dumps(data))
