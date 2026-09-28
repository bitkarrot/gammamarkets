"""Manual NIP-42 AUTH + paid-relay classification (section 9.2, D-26..D-28).

``ClientOptions.automatic_authentication`` stays OFF on every owned
client: automatic AUTH would require a signer (and therefore key
material) attached to long-lived transport. Instead a challenge that
arrives on a live connection is answered by building the kind-22242
event, signing it through ``keystore.sign_event`` inside the operation,
and sending ``ClientMessage.auth`` on the SAME connection only.

Keying rule: the response is keyed to the CONNECTION the challenge
arrived on — the ``relay`` tag is the delivered connection's URL, never a
URL carried inside the challenge or a foreign message. Oversized
challenges are ignored rather than answered. A relay the merchant does
not configure is never authenticated.
"""

from __future__ import annotations

from loguru import logger

from ..db import DomainTransaction, db, table

#: Challenges over 1 KiB are never signed (§9.2 bound).
AUTH_CHALLENGE_MAX_BYTES = 1024

#: D-26..D-28 per-relay auth vocabulary on ``relay_configs.auth_state``.
AUTH_STATES = frozenset(
    {
        "auth-required",
        "auth-sent",
        "authenticated",
        "auth-failed",
        "payment-required",
    }
)


def classify_closed(message: str) -> str | None:
    """A relay CLOSED our REQ — map its reason prefix to the
    ``relay_configs.auth_state`` vocabulary (D-26..D-28)."""
    reason = (message or "").strip().lower()
    if reason.startswith("auth-required"):
        return "auth-required"
    if reason.startswith("payment-required"):
        return "payment-required"
    return None


def classify_relay_ok(message: str) -> tuple[str | None, str | None]:
    """Classify a negative-OK message from a relay.

    A paid-write gate reads as ``payment-required`` — real relays phrase
    it several ways ("paid relay", "payment-required", "payment
    required"). Returns ``(state, invoice)``: invoice is the
    bolt11-shaped token embedded in the message when present (D-27 —
    surfaced, never paid automatically).
    """
    import re

    reason = (message or "").strip().lower()
    if "paid relay" in reason or "payment" in reason:
        invoice = None
        match = re.search(r"\b(lnbc|lntb|lnbcrt|lnsb)[0-9a-zA-Z]+\b", message or "")
        if match:
            invoice = match.group(0)
        return "payment-required", invoice
    return None, None


async def update_relay_auth_state(merchant_id: str, relay_url: str,
                                  state: str, *, note: str | None = None,
                                  invoice: str | None = None) -> None:
    """Persist the per-relay auth surface (D-26..D-28) — bounded state
    vocabulary only."""
    if state not in AUTH_STATES:
        raise ValueError(f"unknown auth_state {state!r}")
    import time as _t

    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('relay_configs')} SET auth_state = :s,"
            " auth_note = :n, paid_invoice = :p, auth_updated_at = :t"
            " WHERE merchant_id = :m AND relay_url = :r",
            {
                "s": state, "n": note, "p": invoice,
                "t": int(_t.time()), "m": merchant_id, "r": relay_url,
            },
        )


async def answer_auth_challenge(client, keystore, merchant_id: str,
                                *, relay_url: str, challenge: str) -> bool:
    """Answer one delivered AUTH challenge through the manual chain.

    Guards (any failure -> return False, nothing signed):
    - ``len(challenge) > 1 KiB``;
    - ``relay_url`` is not an exact member of the client's live
      connection set;
    - the merchant owns no enabled ``inbox``/``both`` relay_config row
      covering that URL (OQ4 — per-merchant auth scoping).

    On success the kind-22242 event is signed inside the keystore op and
    sent via ``ClientMessage.auth``/``send_msg_to`` on the same
    connection; ``relay_configs.auth_state`` moves to ``'auth-sent'``
    (upgraded to ``'authenticated'`` when a post-AUTH REQ is served).
    """
    from nostr_sdk import ClientMessage, EventBuilder, PublicKey, RelayUrl

    if len(challenge.encode()) > AUTH_CHALLENGE_MAX_BYTES:
        logger.info(
            "event=infinitemarkets.inbox.auth_rejected"
            " reason=challenge-oversize"
        )
        return False
    live = {str(u) for u in (await client.relays()).keys()}
    if relay_url not in live:
        logger.info(
            "event=infinitemarkets.inbox.auth_rejected"
            " reason=foreign-connection"
        )
        return False
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT id FROM {table('relay_configs')} "
            "WHERE merchant_id = :m AND relay_url = :r AND enabled"
            " AND direction IN ('inbox', 'both')",
            {"m": merchant_id, "r": relay_url},
        )
        merchant = await conn.fetchone(
            f"SELECT pubkey FROM {table('merchants')} WHERE id = :m",
            {"m": merchant_id},
        )
    if row is None or merchant is None:
        logger.info(
            "event=infinitemarkets.inbox.auth_rejected"
            " reason=unconfigured-relay"
        )
        return False

    builder = EventBuilder.auth(challenge, RelayUrl.parse(relay_url))
    unsigned = builder.build(PublicKey.parse(merchant["pubkey"]))
    signed = await keystore.sign_event(merchant_id, unsigned)
    await client.send_msg_to(
        [RelayUrl.parse(relay_url)], ClientMessage.auth(signed)
    )
    await update_relay_auth_state(merchant_id, relay_url, "auth-sent")
    logger.info(
        "event=infinitemarkets.inbox.auth_answered relay={}",
        relay_url,
    )
    return True
