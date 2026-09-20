"""P0-02 (tracer scope): the one real SDK security probe.

FFI import, keypair generation, event build/sign/verify, tamper rejection,
NIP-44 encrypt/decrypt round-trip, and recording of the tested binary
identity (installed native library filename + SHA-256) into the evidence
pins block.

Plan Task 3 extends this module into the full P0-02 probe set (invalid-event
rejection taxonomy, known-ID admission dedupe, oversized NIP-44 input
bounds, paused-signing AUTH boundedness, and subcheck attribution for the
D-16 disclosure).
"""

from __future__ import annotations

import pytest

from harness import pins as pins_module
from harness import sdk

pytestmark = pytest.mark.sdk


async def test_ffi_import_and_keypair_generation():
    """The FFI import loads and key generation works through the SDK."""
    keys_a = sdk.generate_keys()
    keys_b = sdk.generate_keys()
    assert keys_a.public_key().to_hex() != keys_b.public_key().to_hex()


async def test_build_sign_and_verify_event():
    keys = sdk.generate_keys()
    event = await sdk.sign_text_note(keys, "gamma qualification tracer")
    assert sdk.verify_event(event) is True
    assert event.verify_id() is True
    assert event.verify_signature() is True


async def test_tampered_event_fails_verification():
    keys = sdk.generate_keys()
    event = await sdk.sign_text_note(keys, "original content")
    assert sdk.verify_event(event) is True

    tampered_content = sdk.tamper_event(event, content="tampered content")
    assert sdk.verify_event(tampered_content) is False

    tampered_sig = sdk.tamper_event(event, sig="00" * 64)
    assert sdk.verify_event(tampered_sig) is False
    assert tampered_sig.verify_signature() is False


async def test_nip44_encrypt_decrypt_roundtrip():
    sender = sdk.generate_keys()
    recipient = sdk.generate_keys()
    plaintext = "gamma nip44 roundtrip"
    assert sdk.nip44_roundtrip(sender, recipient, plaintext) == plaintext


async def test_tested_binary_identity_recorded_into_evidence_pins():
    """P0-02: record the tested binary (installed native library identity)."""
    identity = pins_module.record_tested_binary()
    assert identity["filename"], "native library filename must be recorded"
    assert len(identity["sha256"]) == 64, "native library sha256 must be recorded"
    assert identity["size_bytes"] > 0
    # And it landed in the evidence pins block.
    assert pins_module.snapshot()["nostr_sdk_native_library"] == identity
