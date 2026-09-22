"""Merchant domain — section 5.1 semantics over the m001 tables.

- 1:1 merchant per LNbits user (``merchants.user_id`` UNIQUE).
- Wallet binding verified against the host wallet table (exists, belongs to
  the user, ``can_receive_payments``); the stored value is AEAD-encrypted
  with an HMAC equality index — never plaintext.
- Activation state machine: ``draft -> publication_pending -> active ->
  deactivating -> inactive``.
- Every mutation that changes published state enqueues an outbox intent in
  the same domain transaction (section 8.6); publication itself is 02-02.
"""

from __future__ import annotations

import json
import time
import uuid

from .. import crypto
from ..db import DomainTransaction, db, table, topology_supported
from ..security import (
    ProblemError,
    audit_capture_warnings,
    conflict,
    not_found,
    unprocessable,
)
from ..settings import ExtSettings, ext_settings

MERCHANT_STATES = ("draft", "publication_pending", "active", "deactivating", "inactive")
NONTERMINAL_ORDER_STATES = ("received", "invoice_pending", "awaiting_payment",
                            "confirmed", "processing")

MAX_NOTIFY_EMAILS = 5
TEST_SEND_HOURLY_LIMIT = 5


def _now() -> int:
    return int(time.time())


def _keystore(settings: ExtSettings):
    from ..keystore import MerchantKeyStore

    return MerchantKeyStore(settings)


async def _wallet_for_user(wallet_id: str, user_id: str):
    """Host wallet lookup + ownership/receive capability checks."""
    from lnbits.core.crud import get_wallet

    wallet = await get_wallet(wallet_id)
    if not wallet or wallet.user != user_id:
        raise conflict(
            "wallet-mismatch",
            "Wallet mismatch",
            "wallet_id does not belong to the authenticated user",
        )
    if not wallet.can_receive_payments:
        raise conflict(
            "wallet-mismatch",
            "Wallet mismatch",
            "wallet cannot receive payments",
        )
    return wallet


async def _orders_table_exists() -> bool:
    """orders lands in m002 (plan 02-03); absent -> no open orders possible."""
    from lnbits.db import POSTGRES

    async with db.connect() as conn:
        if db.type == POSTGRES:
            row = await conn.fetchone(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'gammamarkets' AND table_name = 'orders'"
            )
        else:
            row = await conn.fetchone(
                "SELECT name FROM gammamarkets.sqlite_master "
                "WHERE type = 'table' AND name = 'orders'"
            )
    return row is not None


async def _blocking_orders(merchant_id: str) -> int:
    if not await _orders_table_exists():
        return 0
    async with db.connect() as conn:
        placeholders = ",".join(f"'{s}'" for s in NONTERMINAL_ORDER_STATES)
        row = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('orders')} "
            f"WHERE merchant_id = :m AND state IN ({placeholders})",
            {"m": merchant_id},
        )
    return int(row["n"]) if row else 0


def _encrypt_wallet_id(
    settings: ExtSettings, merchant_id: str, wallet_id: str
) -> tuple[bytes, str]:
    enc = crypto.encrypt(
        wallet_id.encode(),
        settings.master_keys[settings.active_key_version],
        record_id=merchant_id,
        table="merchants",
        column="wallet_id_enc",
        key_version=settings.active_key_version,
    )
    digest = crypto.hmac_index(
        settings.privacy_key, crypto.PURPOSE_WALLET_ID,
        merchant_id, crypto.normalize(wallet_id),
    )
    return enc, digest


def _public_merchant(row: dict) -> dict:
    """Merchant projection — never includes wallet_id_enc or key material."""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "pubkey": row["pubkey"],
        "display_name": row["display_name"],
        "profile_json": row["profile_json"],
        "payment_preference": row["payment_preference"],
        "recommended_app_d": row["recommended_app_d"],
        "notify_emails": json.loads(row["notify_emails"]) if row["notify_emails"] else [],
        "notify_events": json.loads(row["notify_events"]) if row["notify_events"] else {},
        "state": row["state"],
        "theme": json.loads(row["theme"]) if row.get("theme") else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_merchant_row(merchant_id: str, user_id: str) -> dict:
    """Owner-scoped fetch — 404 (not 403) on foreign ids: no existence leak."""
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('merchants')} WHERE id = :i AND user_id = :u",
            {"i": merchant_id, "u": user_id},
        )
    if not row:
        raise not_found("merchant not found")
    return dict(row)


async def create_merchant(user, *, wallet_id: str, display_name: str | None = None,
                          payment_preference: str = "manual",
                          settings: ExtSettings | None = None) -> dict:
    settings = settings or ext_settings()
    if payment_preference != "manual":
        raise unprocessable(
            "invalid-transition", "Unsupported payment preference",
            "payment_preference is fixed to 'manual' in Release A",
        )
    async with db.connect() as conn:
        existing = await conn.fetchone(
            f"SELECT id FROM {table('merchants')} WHERE user_id = :u",
            {"u": user.id},
        )
    if existing:
        raise conflict(
            "duplicate-merchant", "Merchant exists",
            "a merchant already exists for this user",
        )
    await _wallet_for_user(wallet_id, str(user.id))

    merchant_id = uuid.uuid4().hex
    pubkey = await _keystore(settings).generate(merchant_id)
    wallet_enc, wallet_hash = _encrypt_wallet_id(settings, merchant_id, wallet_id)
    now = _now()

    async with DomainTransaction() as tx:
        await tx.execute(
            f"INSERT INTO {tx.table('merchants')} "
            "(id, user_id, pubkey, key_ref, display_name, payment_preference,"
            " wallet_id_enc, wallet_id_hash, state, created_at, updated_at) "
            "VALUES (:id, :u, :pk, :kr, :dn, 'manual', :we, :wh, 'draft', :t, :t)",
            {
                "id": merchant_id,
                "u": str(user.id),
                "pk": pubkey,
                "kr": f"merchant_keys:{merchant_id}",
                "dn": display_name,
                "we": wallet_enc,
                "wh": wallet_hash,
                "t": now,
            },
        )
    row = await get_merchant_row(merchant_id, str(user.id))
    return _public_merchant(row)


async def current_merchant(user, settings: ExtSettings | None = None) -> dict:
    settings = settings or ext_settings()
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('merchants')} WHERE user_id = :u",
            {"u": str(user.id)},
        )
    if not row:
        raise not_found("no merchant for this user")
    merchant = _public_merchant(dict(row))
    from . import relay as relay_service

    merchant["relay_health"] = await relay_service.relay_health(row["id"])
    merchant["warnings"] = audit_capture_warnings()
    ok, reason = topology_supported()
    if not ok:
        merchant["warnings"].append(f"gammamarkets: {reason}")
        merchant["blocked"] = True
    else:
        merchant["blocked"] = False
    return merchant


async def patch_merchant(merchant_id: str, user, patch: dict,
                         settings: ExtSettings | None = None) -> dict:
    settings = settings or ext_settings()
    row = await get_merchant_row(merchant_id, str(user.id))
    if row["state"] in ("deactivating", "inactive"):
        raise conflict(
            "invalid-transition", "Merchant not editable",
            "merchant is deactivating/inactive",
        )

    allowed = {
        "display_name", "profile_json", "recommended_app_d",
        "notify_emails", "notify_events", "theme", "relay_configs",
        "blossom_servers",
    }
    wallet_id = patch.pop("wallet_id", None)
    unknown = set(patch) - allowed
    if unknown:
        raise unprocessable(
            "unauthorized", "Unknown fields",
            f"unsupported fields: {sorted(unknown)}",
        )
    if "payment_preference" in patch:
        raise unprocessable(
            "invalid-transition", "Unsupported payment preference",
            "payment_preference is fixed to 'manual' in Release A",
        )

    updates: dict = {}
    if wallet_id is not None:
        if await _blocking_orders(merchant_id):
            raise conflict(
                "wallet-mismatch", "Wallet change blocked",
                "open invoice_pending/awaiting_payment orders exist",
            )
        await _wallet_for_user(wallet_id, str(user.id))
        enc, digest = _encrypt_wallet_id(settings, merchant_id, wallet_id)
        updates["wallet_id_enc"] = enc
        updates["wallet_id_hash"] = digest
    if "display_name" in patch:
        updates["display_name"] = patch["display_name"]
    if "profile_json" in patch:
        profile = patch["profile_json"]
        updates["profile_json"] = (
            json.dumps(profile) if not isinstance(profile, str) else profile
        )
    if "recommended_app_d" in patch:
        updates["recommended_app_d"] = patch["recommended_app_d"]
    if "theme" in patch:
        from . import themes as theme_service

        validated = theme_service.validate_theme(patch["theme"])
        updates["theme"] = json.dumps(validated, sort_keys=True)
    if "notify_emails" in patch:
        emails = patch["notify_emails"] or []
        if not isinstance(emails, list) or len(emails) > MAX_NOTIFY_EMAILS:
            raise unprocessable(
                "invalid-transition", "Too many notification addresses",
                f"at most {MAX_NOTIFY_EMAILS} addresses",
            )
        from lnbits.helpers import is_valid_email_address
        for email in emails:
            if not is_valid_email_address(email):
                raise unprocessable(
                    "invalid-transition", "Invalid email address", email
                )
        updates["notify_emails"] = json.dumps(emails)
    if "notify_events" in patch:
        events = patch["notify_events"] or {}
        if not isinstance(events, dict):
            raise unprocessable(
                "invalid-transition", "notify_events must be an object"
            )
        updates["notify_events"] = json.dumps(events)

    relay_configs = patch.pop("relay_configs", None) if "relay_configs" in patch else None
    blossom_servers = (
        patch.pop("blossom_servers", None)
        if "blossom_servers" in patch
        else None
    )

    async with DomainTransaction() as tx:
        for col, val in updates.items():
            await tx.execute(
                f"UPDATE {tx.table('merchants')} SET {col} = :v, "
                "updated_at = :t WHERE id = :i",
                {"v": val, "t": _now(), "i": merchant_id},
            )
        if relay_configs is not None:
            await _replace_relay_configs(tx, merchant_id, relay_configs)
        # Profile-affecting changes enqueue a kind-0 republication intent.
        if updates.keys() & {
            "display_name", "profile_json", "recommended_app_d", "theme"
        }:
            await _enqueue_intent(
                tx, merchant_id, "merchant_profile", merchant_id, 0
            )
    if blossom_servers is not None:
        # media endpoints persist outside relay_configs (spec delta —
        # blossom is https, not a nostr relay)
        from . import relay as relay_service

        await relay_service.set_blossom_servers(merchant_id, blossom_servers)
    row = await get_merchant_row(merchant_id, str(user.id))
    return _public_merchant(row)


async def _replace_relay_configs(tx: DomainTransaction, merchant_id: str,
                                 configs: list) -> None:
    if not isinstance(configs, list):
        raise unprocessable(
            "invalid-relay", "relay_configs must be a list"
        )
    normalized = []
    seen = set()
    for cfg in configs:
        if not isinstance(cfg, dict) or "relay_url" not in cfg:
            raise unprocessable(
                "invalid-relay", "each relay_config needs relay_url"
            )
        from .transport import validate_relay_target

        url = validate_relay_target(cfg["relay_url"])
        direction = cfg.get("direction", "public")
        if direction not in ("public", "inbox", "both"):
            raise unprocessable(
                "invalid-relay", "direction must be public|inbox|both"
            )
        enabled = bool(cfg.get("enabled", True))
        if (url, direction) in seen:
            raise unprocessable(
                "invalid-relay", "duplicate relay_config entry"
            )
        seen.add((url, direction))
        normalized.append((url, direction, enabled))

    await tx.execute(
        f"DELETE FROM {tx.table('relay_configs')} WHERE merchant_id = :m",
        {"m": merchant_id},
    )
    for url, direction, enabled in normalized:
        await tx.execute(
            f"INSERT INTO {tx.table('relay_configs')} "
            "(id, merchant_id, relay_url, direction, enabled, created_at,"
            " updated_at) VALUES (:i, :m, :u, :d, :e, :t, :t)",
            {
                "i": uuid.uuid4().hex,
                "m": merchant_id,
                "u": url,
                "d": direction,
                "e": enabled,
                "t": _now(),
            },
        )


async def _enqueue_intent(tx: DomainTransaction, merchant_id: str,
                          aggregate_type: str, aggregate_id: str,
                          event_kind: int,
                          revision: int = 0,
                          event_address: str | None = None) -> str:
    """Insert a pending outbox intent inside the caller's transaction."""
    from .outbox import enqueue_intent

    return await enqueue_intent(
        tx, merchant_id, aggregate_type, aggregate_id, event_kind,
        revision=revision, event_address=event_address,
    )


async def import_nsec(merchant_id: str, user, nsec_bech32: str,
                    settings: ExtSettings | None = None) -> dict:
    """Replace the merchant key with an imported nsec (section 11).

    The body is never logged (Pitfall 8); the merchant pubkey updates to the
    imported identity and a profile republication intent is enqueued.
    """
    settings = settings or ext_settings()
    row = await get_merchant_row(merchant_id, str(user.id))
    if row["state"] in ("deactivating", "inactive"):
        raise conflict(
            "invalid-transition", "Merchant not editable",
            "merchant is deactivating/inactive",
        )
    pubkey = await _keystore(settings).import_key(merchant_id, nsec_bech32)
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('merchants')} SET pubkey = :p, updated_at = :t "
            "WHERE id = :i",
            {"p": pubkey, "t": _now(), "i": merchant_id},
        )
        await _enqueue_intent(
            tx, merchant_id, "merchant_profile", merchant_id, 0
        )
    row = await get_merchant_row(merchant_id, str(user.id))
    return _public_merchant(row)


async def publish(merchant_id: str, user,
                  settings: ExtSettings | None = None) -> dict:
    """Enqueue republication intents for all merchant aggregates and move
    ``draft -> publication_pending`` (02-02 publishes + flips active)."""
    row = await get_merchant_row(merchant_id, str(user.id))
    if row["state"] in ("deactivating", "inactive"):
        raise conflict(
            "invalid-transition", "Merchant not publishable",
            f"merchant state is {row['state']}",
        )
    now = _now()
    # Owner directive: merchants with no configured relays are seeded with
    # the visible starter set (editable rows — no hidden fallback).
    from . import relay as relay_service

    await relay_service.ensure_default_relays(merchant_id)
    async with DomainTransaction() as tx:
        # Merchant profile + NIP-89 handler pair are always republished;
        # catalog aggregates are enqueued by services/catalog.py on their
        # own mutations — a full republish enqueues one per live aggregate.
        for kind in (0, 31989, 31990):
            await _enqueue_intent(
                tx, merchant_id, "merchant_profile", merchant_id, kind
            )
        for agg_table, kind in (
            ("products", 30402), ("collections", 30405), ("shipping_options", 30406),
        ):
            rows = await tx.fetch_all(
                f"SELECT id, revision FROM {tx.table(agg_table)} "
                "WHERE merchant_id = :m AND deleted_at IS NULL",
                {"m": merchant_id},
            )
            for r in rows:
                await _enqueue_intent(
                    tx, merchant_id, agg_table, r["id"], kind,
                    revision=r["revision"],
                )
        # NIP-15 projection: stall + products for nip15-enabled catalogs
        nip15_catalogs = await tx.fetch_all(
            f"SELECT id FROM {tx.table('catalogs')} "
            "WHERE merchant_id = :m AND publish_nip15 AND deleted_at IS NULL",
            {"m": merchant_id},
        )
        for cat in nip15_catalogs:
            await _enqueue_intent(
                tx, merchant_id, "catalogs", cat["id"], 30017
            )
            prods = await tx.fetch_all(
                f"SELECT id, revision FROM {tx.table('products')} "
                "WHERE catalog_id = :c AND merchant_id = :m"
                " AND deleted_at IS NULL",
                {"c": cat["id"], "m": merchant_id},
            )
            for r in prods:
                await _enqueue_intent(
                    tx, merchant_id, "products", r["id"], 30018,
                    revision=r["revision"],
                )
        if row["state"] == "draft":
            await tx.execute(
                f"UPDATE {tx.table('merchants')} "
                "SET state = 'publication_pending', updated_at = :t "
                "WHERE id = :i AND state = 'draft'",
                {"t": now, "i": merchant_id},
            )
    return {"enqueued": True, "state": "publication_pending"}


async def get_notifications(merchant_id: str, user) -> dict:
    row = await get_merchant_row(merchant_id, str(user.id))
    from ..db import db, table

    async with db.connect() as conn:
        queue_rows = await conn.fetchall(
            f"SELECT event_type, channel, state, attempts, last_error,"
            f" created_at, order_id FROM {table('email_queue')}"
            " WHERE merchant_id = :m ORDER BY created_at DESC LIMIT 50",
            {"m": merchant_id},
        )
    return {
        "notify_emails": json.loads(row["notify_emails"])
        if row["notify_emails"] else [],
        "notify_events": json.loads(row["notify_events"])
        if row["notify_events"] else {},
        "queue": [
            {
                "event_type": r["event_type"],
                "channel": r["channel"],
                "state": r["state"],
                "attempts": r["attempts"],
                "last_error": r["last_error"],
                "created_at": r["created_at"],
                "order_bound": r["order_id"] is not None,
            }
            for r in queue_rows
        ],
    }


async def send_test_notification(merchant_id: str, user, recipient: str,
                                 settings: ExtSettings | None = None) -> dict:
    """Bounded test send — ≤5/hour per merchant via rate_limit_buckets,
    enqueued through the durable §8.8 email path."""
    settings = settings or ext_settings()
    row = await get_merchant_row(merchant_id, str(user.id))
    from lnbits.helpers import is_valid_email_address
    if not is_valid_email_address(recipient):
        raise unprocessable(
            "invalid-transition", "Invalid email address", recipient
        )
    allowed = json.loads(row["notify_emails"]) if row["notify_emails"] else []
    if recipient not in allowed:
        raise unprocessable(
            "invalid-transition", "Unknown recipient",
            "test sends only go to configured notify_emails",
        )

    now = _now()
    window = now - (now % 3600)
    async with DomainTransaction() as tx:
        bucket = await tx.fetch_one(
            f"SELECT count FROM {tx.table('rate_limit_buckets')} "
            "WHERE scope_hash = :s AND bucket = 'test-send' AND window_start = :w",
            {
                "s": crypto.hmac_index(
                    settings.privacy_key, crypto.PURPOSE_EMAIL_RECIPIENT,
                    merchant_id, crypto.normalize(recipient),
                ),
                "w": window,
            },
        )
        count = bucket["count"] if bucket else 0
        if count >= TEST_SEND_HOURLY_LIMIT:
            raise ProblemError(
                429, "rate-limited", "Rate limited",
                "test send limit reached",
            )
        if bucket:
            await tx.execute(
                f"UPDATE {tx.table('rate_limit_buckets')} SET count = count + 1 "
                "WHERE scope_hash = :s AND bucket = 'test-send' "
                "AND window_start = :w",
                {
                    "s": crypto.hmac_index(
                        settings.privacy_key, crypto.PURPOSE_EMAIL_RECIPIENT,
                        merchant_id, crypto.normalize(recipient),
                    ),
                    "w": window,
                },
            )
        else:
            await tx.execute(
                f"INSERT INTO {tx.table('rate_limit_buckets')} "
                "(scope_hash, bucket, window_start, count, expires_at) "
                "VALUES (:s, 'test-send', :w, 1, :e)",
                {
                    "s": crypto.hmac_index(
                        settings.privacy_key, crypto.PURPOSE_EMAIL_RECIPIENT,
                        merchant_id, crypto.normalize(recipient),
                    ),
                    "w": window,
                    "e": window + 7200,
                },
            )

    # Enqueue through the durable §8.8 path (orderless rows bind recipient
    # decryption to merchant_id) — the worker handles suppression and
    # host-SMTP gating at send time.
    from . import email as email_service

    row_id = await email_service.enqueue_test_send(
        merchant_id=merchant_id, recipient=recipient, now=now,
    )
    return {"sent": False, "queued": True, "queue_id": row_id}


async def begin_deactivation(merchant_id: str, user) -> dict:
    """Two-step deactivation (section 6.7): report blockers, mark
    deactivating. Key destruction requires durable tombstones (later step)."""
    row = await get_merchant_row(merchant_id, str(user.id))
    if row["state"] == "inactive":
        return {"state": "inactive", "blockers": []}
    blockers: list[dict] = []
    open_orders = await _blocking_orders(merchant_id)
    if open_orders:
        blockers.append(
            {"type": "open-orders", "count": open_orders}
        )
    if row["state"] != "deactivating":
        if blockers:
            raise conflict(
                "invalid-transition", "Deactivation blocked",
                json.dumps(blockers),
            )
        async with DomainTransaction() as tx:
            await tx.execute(
                f"UPDATE {tx.table('merchants')} SET state = 'deactivating',"
                " updated_at = :t WHERE id = :i",
                {"t": _now(), "i": merchant_id},
            )
            # Tombstone intents for every live aggregate (section 6.7).
            for agg_table, kind in (
                ("products", 5), ("collections", 5), ("shipping_options", 5),
            ):
                rows = await tx.fetch_all(
                    f"SELECT id, revision FROM {tx.table(agg_table)} "
                    "WHERE merchant_id = :m AND deleted_at IS NULL",
                    {"m": merchant_id},
                )
                for r in rows:
                    await _enqueue_intent(
                        tx, merchant_id, agg_table, r["id"], kind,
                        revision=r["revision"],
                    )
    return {"state": "deactivating", "blockers": blockers}
