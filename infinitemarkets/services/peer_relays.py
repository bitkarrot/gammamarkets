"""Buyer kind-10050 relay-route discovery (D-30, spec section 9.3).

A buyer's current inbox relay set is discovered from kind-10050 events on
the merchant's configured discovery relays (the enabled public set). The
result is cached in ``peer_relays`` for ``settings.peer_relay_ttl``
seconds — never re-fetched inside a send hot path.

Hard rules:

- every candidate relay URL is normalized ``wss://`` AND DNS-resolved to
  public routable space at discovery time
  (``validate_peer_relay_target`` — IPv4+IPv6, loopback/private/
  link-local/multicast/reserved/169.254.169.254 all rejected); the same
  check runs again before any send connects;
- ``NO_INBOX_RELAYS`` is the explicit sentinel result — consumers must
  never fall back to the source relay or any unvalidated target;
- only signature-valid kind-10050s authored by the buyer carry routes.
"""

from __future__ import annotations

import time
import uuid

from .. import crypto
from ..db import DomainTransaction, db, table
from ..settings import ext_settings
from .transport import validate_peer_relay_target

#: Explicit no-route sentinel — returned instead of a list when discovery
#: found nothing usable. Callers (03-02 outbound wrap path) branch on it;
#: it is never a valid relay URL.
NO_INBOX_RELAYS = "no_inbox_relays"


def _now() -> int:
    return int(time.time())


def _pubkey_hash(settings, merchant_id: str, pubkey_hex: str) -> str:
    return crypto.hmac_index(
        settings.privacy_key, crypto.PURPOSE_BUYER_PUBKEY,
        merchant_id, crypto.normalize(pubkey_hex),
    )


def _extract_routes(event) -> list[str] | None:
    """Signature + shape check on a kind-10050 event; returns the relay
    tag values or None when the event cannot carry routes."""
    if event.kind().as_u16() != 10050:
        return None
    if not event.verify():
        return None
    relays = [
        tag.as_vec()[1]
        for tag in event.tags().to_vec()
        if tag.as_vec() and tag.as_vec()[0] == "relay"
        and len(tag.as_vec()) >= 2
    ]
    if not 1 <= len(relays) <= 3:
        return None
    return relays


async def _cached_routes(merchant_id: str, pubkey_hash: str,
                         now: int) -> list[str] | None:
    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT relay_url FROM {table('peer_relays')} "
            "WHERE merchant_id = :m AND pubkey_hash = :h "
            "AND expires_at > :n ORDER BY relay_url",
            {"m": merchant_id, "h": pubkey_hash, "n": now},
        )
    urls = [r["relay_url"] for r in rows]
    return urls or None


async def _store_routes(settings, merchant_id: str, pubkey_hex: str,
                        pubkey_hash: str, urls: list[str],
                        now: int) -> None:
    key = settings.master_keys[settings.active_key_version]
    ver = settings.active_key_version
    async with DomainTransaction() as tx:
        # Drop stale rows for this peer first — the route set replaces
        # whatever a previous advertisement cached.
        await tx.execute(
            f"DELETE FROM {tx.table('peer_relays')} "
            "WHERE merchant_id = :m AND pubkey_hash = :h",
            {"m": merchant_id, "h": pubkey_hash},
        )
        for url in urls:
            row_id = uuid.uuid4().hex
            pubkey_enc = crypto.encrypt(
                pubkey_hex.encode(), key, record_id=row_id,
                table="peer_relays", column="pubkey_enc", key_version=ver,
            )
            await tx.execute(
                f"INSERT INTO {tx.table('peer_relays')} (id,"
                " merchant_id, pubkey_hash, pubkey_enc, relay_url,"
                " fetched_at, expires_at) "
                "VALUES (:i, :m, :h, :e, :u, :f, :x)",
                {
                    "i": row_id, "m": merchant_id, "h": pubkey_hash,
                    "e": pubkey_enc, "u": url, "f": now,
                    "x": now + settings.peer_relay_ttl,
                },
            )


async def resolve_buyer_inbox_relays(
    merchant_id: str, buyer_pubkey_hex: str, *, settings=None,
    discovery_timeout_s: float = 10,
) -> list[str] | str:
    """Resolve the buyer's kind-10050 inbox relays.

    Returns the validated route list, or the ``NO_INBOX_RELAYS``
    sentinel — a failed/zero-target/malformed discovery never falls back
    to any unvalidated relay.
    """
    from nostr_sdk import Filter, Kind, PublicKey

    from . import relay as relay_service
    from .transport import transport

    settings = settings or ext_settings()
    now = _now()
    pubkey_hash = _pubkey_hash(settings, merchant_id, buyer_pubkey_hex)

    cached = await _cached_routes(merchant_id, pubkey_hash, now)
    if cached is not None:
        return cached

    discovery_urls = await relay_service.relay_targets(
        merchant_id, "public"
    )
    if not discovery_urls:
        return NO_INBOX_RELAYS

    nostr_filter = (
        Filter()
        .kinds([Kind(10050)])
        .author(PublicKey.parse(buyer_pubkey_hex))
    )
    events = await transport().fetch_from(
        discovery_urls, nostr_filter, timeout_s=discovery_timeout_s
    )
    # Latest-created_at first — a newer advertisement supersedes.
    events.sort(key=lambda e: e.created_at().as_secs(), reverse=True)
    for event in events:
        if event.author().to_hex() != buyer_pubkey_hex:
            continue
        candidates = _extract_routes(event)
        if candidates is None:
            continue
        normalized: list[str] = []
        try:
            for url in candidates:
                normalized.append(await validate_peer_relay_target(url))
        except Exception:
            continue  # a non-public / non-wss advertisement carries no route
        await _store_routes(
            settings, merchant_id, buyer_pubkey_hex, pubkey_hash,
            normalized, now,
        )
        return normalized
    return NO_INBOX_RELAYS


async def refresh_stale_peer_relays(*, settings=None) -> dict:
    """The TTL refresh cycle + the §9.3 no-route sweep.

    Expired cache rows are dropped and re-resolved once per (merchant,
    peer). ``order_msg`` intents stuck ``pending``/``partially_published``
    on ``no_inbox_relays`` get their recipient's kind-10050 set
    force-refreshed (cached rows deleted first) so a buyer who advertises
    routes mid-window is discovered on this 15-min cadence rather than at
    TTL expiry; intents older than the 48h no-route deadline fail
    terminally. Buyer pubkeys live under AEAD (``pubkey_enc``/
    ``payload_enc``) and are decrypted inside this operation only."""
    import json as _json

    from .outbox import ORDER_MSG_NO_ROUTE_DEADLINE_S

    settings = settings or ext_settings()
    now = _now()
    stats = {"refreshed": 0, "failed": 0,
             "no_route_refreshed": 0, "no_route_failed": 0}
    async with db.connect() as conn:
        stale = await conn.fetchall(
            f"SELECT DISTINCT merchant_id, pubkey_hash"
            f" FROM {table('peer_relays')} WHERE expires_at <= :n",
            {"n": now},
        )
    for peer in stale:
        async with db.connect() as conn:
            row = await conn.fetchone(
                f"SELECT id, pubkey_enc FROM {table('peer_relays')} "
                "WHERE merchant_id = :m AND pubkey_hash = :h LIMIT 1",
                {"m": peer["merchant_id"], "h": peer["pubkey_hash"]},
            )
        if row is None:
            continue
        try:
            pubkey_hex = crypto.decrypt(
                bytes(row["pubkey_enc"]),
                settings.master_keys[settings.active_key_version],
                record_id=row["id"], table="peer_relays",
                column="pubkey_enc",
                key_version=settings.active_key_version,
            ).decode()
            # resolve re-fetches because the expired rows were deleted
            # inside _store_routes only after a fresh advertisement —
            # delete now to bypass the cache first.
            async with DomainTransaction() as tx:
                await tx.execute(
                    f"DELETE FROM {tx.table('peer_relays')} "
                    "WHERE merchant_id = :m AND pubkey_hash = :h",
                    {"m": peer["merchant_id"], "h": peer["pubkey_hash"]},
                )
            await resolve_buyer_inbox_relays(
                peer["merchant_id"], pubkey_hex, settings=settings
            )
            stats["refreshed"] += 1
        except Exception:  # noqa: BLE001 — report-only per peer
            stats["failed"] += 1

    # §9.3 no-route sweep: pending order_msg intents whose recipient had
    # no declared inbox set at the last attempt get a fresh kind-10050
    # fetch (cache rows deleted first — a stale-but-unexpired set must not
    # pin the old routes for the whole TTL). Past the 48h deadline from
    # first enqueue the intent fails terminally.
    async with db.connect() as conn:
        stuck = await conn.fetchall(
            f"SELECT id, merchant_id, created_at, payload_enc"
            f" FROM {table('outbox_events')}"
            " WHERE aggregate_type = 'order_msg'"
            " AND state IN ('pending', 'partially_published')"
            " AND last_error = 'no_inbox_relays'",
        )
    for intent in stuck:
        intent = dict(intent)
        try:
            if now - int(intent["created_at"]) >= (
                ORDER_MSG_NO_ROUTE_DEADLINE_S
            ):
                async with DomainTransaction() as tx:
                    await tx.execute(
                        f"UPDATE {tx.table('outbox_events')} SET"
                        " state = 'failed', next_attempt_at = 0,"
                        " claimed_by = NULL, claimed_until = NULL,"
                        " updated_at = :n"
                        " WHERE id = :i AND last_error = 'no_inbox_relays'"
                        " AND state IN ('pending', 'partially_published')",
                        {"n": now, "i": intent["id"]},
                    )
                stats["no_route_failed"] += 1
                continue
            if intent["payload_enc"] is None:
                continue
            ver = crypto.envelope_version(intent["payload_enc"])
            descriptor = _json.loads(
                crypto.decrypt(
                    intent["payload_enc"],
                    settings.master_keys[ver],
                    record_id=intent["id"], table="outbox_events",
                    column="payload_enc", key_version=ver,
                ).decode()
            )
            recipient = descriptor.get("recipient_pubkey")
            if not recipient:
                continue
            pubkey_hash = _pubkey_hash(
                settings, intent["merchant_id"], recipient
            )
            async with DomainTransaction() as tx:
                await tx.execute(
                    f"DELETE FROM {tx.table('peer_relays')} "
                    "WHERE merchant_id = :m AND pubkey_hash = :h",
                    {"m": intent["merchant_id"], "h": pubkey_hash},
                )
            await resolve_buyer_inbox_relays(
                intent["merchant_id"], recipient, settings=settings
            )
            stats["no_route_refreshed"] += 1
        except Exception as exc:  # noqa: BLE001 — report-only per intent
            stats["failed"] += 1
            stats["last_error"] = type(exc).__name__
    return stats
