"""Public checkout — spec sections 8.1, 8.2, 4.15, 11.4, 15.

The intake/claim/invoice pipeline:

1. ``Idempotency-Key`` validation + ``idempotency_records`` unique-insert
   claim BEFORE any order row exists (§4.15). Replay returns the stored
   (AEAD-encrypted) response; concurrent in-flight requests get 409
   ``request-in-progress``; key reuse with a different body gets 409
   ``idempotency-conflict``.
2. Intake validation (§8.1/§15): bounded items, merchant active, products
   purchasable, address required iff physical, ``email_opt_in`` requires
   ``email``, shipping option valid for the destination.
3. Server-side totals only — client-sent amounts are never trusted.
4. Intake transaction: orders(received) + items + fx snapshots + audit
   event + token material + ``order_received`` email intents.
5. Claim transaction (§8.2 step 1): sorted-product-id conditional stock
   updates + held reservations + CAS ``received -> invoice_pending`` + the
   ``payments`` projection with deterministic ``core_external_id`` and
   ``status='creating'`` — all BEFORE the LNbits call.
6. ``create_invoice`` outside any transaction; ``InvoiceError.status``
   drives the outcome split — ``failed`` is definitive, ``pending``/other
   exceptions are ``creation_unknown`` (never a second invoice).
7. Attach transaction: projection fields persisted regardless of commerce
   state; ``awaiting_payment`` only for a still-``invoice_pending`` order.

Public tokens (§11.4): minted once at intake; only the SHA-256 lookup hash
plus an AEAD copy (for eligible delayed email rendering) are stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid

from .. import crypto
from ..db import DomainTransaction, db, table
from ..security import ProblemError, conflict, not_found, unprocessable
from ..settings import ExtSettings, ext_settings
from . import fx
from . import orders as order_service

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
REGION_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")

MAX_ITEMS = 64
MAX_QTY = 10_000
MAX_OPEN_ORDERS_PER_SCOPE = 10
MAX_HELD_PER_PRODUCT = 100
IDEMPOTENCY_LEASE_S = 120
IDEMPOTENCY_TTL_S = 30 * 86400
TOKEN_TTL_S = 30 * 86400
INVOICE_MEMO = "GammaMarkets order"


def _now() -> int:
    return int(time.time())


# --- idempotency (section 4.15) -------------------------------------------


def _scope_hash(merchant_id: str, route: str, key: str) -> str:
    """SHA-256 of merchant + method + normalized route + idempotency key.

    IP is never part of idempotency identity (§4.15).
    """
    return hashlib.sha256(
        f"{merchant_id}|POST|{route}|{key}".encode()
    ).hexdigest()


def _request_hash(payload: dict) -> str:
    """Canonical immutable request hash for conflict detection."""
    canonical = json.dumps(
        {
            "merchant_pubkey": payload.get("merchant_pubkey"),
            "items": payload.get("items"),
            "shipping_option_d": payload.get("shipping_option_d"),
            "address": payload.get("address"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "email_opt_in": payload.get("email_opt_in"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _claim_idempotency(
    scope: str, request_hash: str, *, now: int
) -> dict | None:
    """Claim the idempotency record; returns a completed record to replay.

    Raises 409 ``request-in-progress`` while a lease is live and 409
    ``idempotency-conflict`` on key reuse with a different request hash.
    An expired lease is reclaimed (state flips back to in_progress with a
    fresh lease) — the linked order, if any, resumes through the saga.
    """
    async with DomainTransaction() as tx:
        row = await tx.fetch_one(
            f"SELECT * FROM {tx.table('idempotency_records')} "
            "WHERE scope_hash = :s",
            {"s": scope},
        )
        if row is None:
            await tx.execute(
                f"INSERT INTO {tx.table('idempotency_records')} "
                "(scope_hash, request_hash, state, lease_until, created_at,"
                " expires_at) "
                "VALUES (:s, :r, 'in_progress', :l, :n, :e)",
                {
                    "s": scope,
                    "r": request_hash,
                    "l": now + IDEMPOTENCY_LEASE_S,
                    "n": now,
                    "e": now + IDEMPOTENCY_TTL_S,
                },
            )
            return None
        if row["request_hash"] != request_hash:
            raise conflict(
                "idempotency-conflict", "Idempotency conflict",
                "this key was already used with a different request",
            )
        if row["state"] == "completed" and row["response_enc"] is not None:
            return dict(row)
        if (
            row["state"] == "in_progress"
            and row["lease_until"]
            and row["lease_until"] > now
        ):
            raise conflict(
                "request-in-progress", "Request in progress",
                "an identical request is still being processed",
            )
        # Expired lease or failed attempt — reclaim with the same hash.
        rc = await tx.execute(
            f"UPDATE {tx.table('idempotency_records')} "
            "SET state = 'in_progress', lease_until = :l WHERE scope_hash = :s",
            {"s": scope, "l": now + IDEMPOTENCY_LEASE_S},
        )
        if rc != 1:
            raise conflict(
                "request-in-progress", "Request in progress",
                "an identical request is still being processed",
            )
        if row["order_id"]:
            # A crashed lease with a linked order resumes through the saga —
            # never restart the intake blindly (§4.15).
            return {"_resume_order_id": row["order_id"], **row}
        return None


async def _complete_idempotency(
    scope: str, *, order_id: str, status_code: int, response_body: dict,
    settings: ExtSettings, now: int,
) -> None:
    enc = crypto.encrypt(
        json.dumps(response_body).encode(),
        settings.master_keys[settings.active_key_version],
        record_id=scope, table="idempotency_records",
        column="response_enc", key_version=settings.active_key_version,
    )
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('idempotency_records')} "
            "SET state = 'completed', order_id = :o, status_code = :c,"
            " response_enc = :r, lease_until = 0 WHERE scope_hash = :s",
            {"s": scope, "o": order_id, "c": status_code, "r": enc},
        )


async def _fail_idempotency(scope: str) -> None:
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('idempotency_records')} "
            "SET state = 'failed', lease_until = 0 WHERE scope_hash = :s",
            {"s": scope},
        )


async def replay_response(record: dict) -> dict | None:
    """Decrypt a stored idempotent response (§4.15)."""
    if record.get("response_enc") is None:
        return None
    settings = ext_settings()
    ver = crypto.envelope_version(record["response_enc"])
    raw = crypto.decrypt(
        record["response_enc"], settings.master_keys[ver],
        record_id=record["scope_hash"], table="idempotency_records",
        column="response_enc", key_version=ver,
    )
    return json.loads(raw)


# --- intake validation (sections 8.1, 15) ----------------------------------


def validate_idempotency_key(key: str | None) -> str:
    """§5.4: checkout without a valid Idempotency-Key is a 400."""
    if not key or not IDEMPOTENCY_KEY_RE.match(key):
        raise ProblemError(
            400, "idempotency-key-required", "Bad Request",
            "Idempotency-Key must match [A-Za-z0-9_-]{32,128}",
        )
    return key


async def _merchant_for_checkout(pubkey: str) -> dict:
    from .nip89 import merchant_by_pubkey

    merchant = await merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] != "active":
        raise unprocessable(
            "merchant-inactive", "Merchant unavailable",
            "merchant is not accepting orders",
        )
    return merchant


async def _resolve_items(
    merchant_id: str, items: list[dict],
) -> list[dict]:
    """Resolve each ``{d_tag, quantity}`` to a purchasable product."""
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
        raise unprocessable(
            "invalid-content", "Invalid items",
            f"items must be a non-empty list of at most {MAX_ITEMS}",
        )
    resolved = []
    async with db.connect() as conn:
        for entry in items:
            if not isinstance(entry, dict):
                raise unprocessable("invalid-content", "Invalid item")
            d_tag = entry.get("d_tag")
            qty = entry.get("quantity")
            if not isinstance(d_tag, str) or not isinstance(qty, int):
                raise unprocessable("invalid-content", "Invalid item")
            if qty < 1 or qty > MAX_QTY:
                raise unprocessable(
                    "invalid-content", "Invalid quantity",
                    f"quantity must be 1..{MAX_QTY}",
                )
            row = await conn.fetchone(
                f"SELECT * FROM {table('products')} "
                "WHERE merchant_id = :m AND d_tag = :d",
                {"m": merchant_id, "d": d_tag},
            )
            if not row or row["deleted_at"] is not None:
                raise not_found("product not found")
            product = dict(row)
            _assert_purchasable(product)
            resolved.append({"product": product, "qty": qty})
    # A variation's parent must remain variable and on-sale.
    async with db.connect() as conn:
        for entry in resolved:
            p = entry["product"]
            if p["product_type"] == "variation":
                parent = await conn.fetchone(
                    f"SELECT product_type, visibility, deleted_at FROM"
                    f" {table('products')} WHERE id = :i",
                    {"i": p["parent_product_id"]},
                )
                if (
                    not parent
                    or parent["product_type"] != "variable"
                    or parent["visibility"] != "on-sale"
                    or parent["deleted_at"] is not None
                ):
                    raise unprocessable(
                        "product-inactive", "Product unavailable",
                        "variation parent is not on-sale",
                    )
    return resolved


def _assert_purchasable(product: dict) -> None:
    """Section 8.1 step 5: v1 purchasability rules."""
    if product["draft"]:
        raise unprocessable("product-inactive", "Product unavailable")
    if product["visibility"] != "on-sale":
        raise unprocessable(
            "product-inactive", "Product unavailable",
            "only on-sale products are purchasable in v1",
        )
    if product["nip99_status"] != "active":
        raise unprocessable("product-inactive", "Product unavailable")
    if product["recurring_frequency"] is not None:
        raise unprocessable(
            "product-inactive", "Product unavailable",
            "subscriptions are not supported in v1",
        )
    if product["product_type"] == "variable":
        raise unprocessable(
            "product-inactive", "Product unavailable",
            "a variable parent is never directly purchasable",
        )
    if product["product_type"] not in ("simple", "variation"):
        raise unprocessable("product-inactive", "Product unavailable")


async def _resolve_shipping(
    merchant_id: str, d_tag: str, address: dict,
) -> dict:
    """Resolve + coverage-check one active same-merchant shipping option."""
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('shipping_options')} "
            "WHERE merchant_id = :m AND d_tag = :d AND deleted_at IS NULL",
            {"m": merchant_id, "d": d_tag},
        )
    if not row or not row["active"]:
        raise unprocessable(
            "invalid-shipping-destination", "Shipping unavailable",
            "shipping option not found or inactive",
        )
    option = dict(row)
    country = (address.get("country") or "").upper()
    if not COUNTRY_RE.match(country):
        raise unprocessable(
            "invalid-shipping-destination", "Invalid destination",
            "address.country must be ISO 3166-1 alpha-2",
        )
    region = address.get("region")
    if region is not None and not REGION_RE.match(str(region).upper()):
        raise unprocessable(
            "invalid-shipping-destination", "Invalid destination",
            "address.region must be ISO 3166-2",
        )
    countries = json.loads(option["countries"]) if option["countries"] else []
    if countries and country not in countries:
        raise unprocessable(
            "invalid-shipping-destination", "Invalid destination",
            "shipping option does not cover this country",
        )
    regions = json.loads(option["regions"]) if option["regions"] else []
    if regions and region and str(region).upper() not in regions:
        raise unprocessable(
            "invalid-shipping-destination", "Invalid destination",
            "shipping option does not cover this region",
        )
    return option


def _check_shipping_constraints(option: dict, resolved: list[dict]) -> None:
    """Weight/dimension bounds across the whole cart (§8.1 step 7)."""
    total_weight = 0.0
    for entry in resolved:
        p = entry["product"]
        if p["format"] != "physical":
            continue
        if p["weight_value"] is not None:
            total_weight += p["weight_value"] * entry["qty"]
        for key, col in (("dim_l", "dim_max_l"), ("dim_w", "dim_max_w"),
                         ("dim_h", "dim_max_h")):
            if option[col] is not None and p[key] is not None:
                if p[key] > option[col]:
                    raise unprocessable(
                        "invalid-shipping-destination",
                        "Invalid destination",
                        "item dimensions exceed the shipping option maximum",
                    )
    if option["weight_max"] is not None and total_weight > option["weight_max"]:
        raise unprocessable(
            "invalid-shipping-destination", "Invalid destination",
            "cart weight exceeds the shipping option maximum",
        )


async def _open_order_count(merchant_id: str, scope_hash: str) -> int:
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('orders')} "
            "WHERE merchant_id = :m AND protocol = 'web'"
            " AND checkout_scope_hash = :s"
            " AND state IN ('received', 'invoice_pending',"
            " 'awaiting_payment')",
            {"m": merchant_id, "s": scope_hash},
        )
    return int(row["n"]) if row else 0


async def _held_reservation_count(product_id: str) -> int:
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('inventory_reservations')} "
            "WHERE product_id = :p AND state = 'held'",
            {"p": product_id},
        )
    return int(row["n"]) if row else 0


# --- the checkout pipeline --------------------------------------------------


async def checkout(
    *,
    payload: dict,
    idempotency_key: str,
    client_scope: str,
    now: int | None = None,
) -> dict:
    """Run the §8.1/§8.2 checkout pipeline; returns the §5.4 201 body."""
    settings = ext_settings()
    now = _now() if now is None else now
    route = "/api/v1/public/checkout"

    merchant = await _merchant_for_checkout(payload.get("merchant_pubkey") or "")
    scope = _scope_hash(merchant["id"], route, idempotency_key)
    request_hash = _request_hash(payload)
    record = await _claim_idempotency(scope, request_hash, now=now)
    if record is not None:
        if "_resume_order_id" in record:
            body = await _resume_order(record, now=now)
            await _complete_idempotency(
                scope, order_id=record["_resume_order_id"],
                status_code=201, response_body=body,
                settings=settings, now=_now(),
            )
            return body
        body = await replay_response(record)
        if body is not None:
            return body

    try:
        body = await _run_checkout(
            merchant=merchant, payload=payload,
            client_scope=client_scope, settings=settings, now=now,
        )
    except Exception:
        await _fail_idempotency(scope)
        raise
    await _complete_idempotency(
        scope, order_id=body["_order_id"], status_code=201,
        response_body=body["response"], settings=settings, now=_now(),
    )
    return body["response"]


async def _run_checkout(
    *,
    merchant: dict,
    payload: dict,
    client_scope: str,
    settings: ExtSettings,
    now: int,
) -> dict:
    """Intake -> totals -> tx1 order -> saga -> response."""
    # Open-order cap (§15): ≤10 unpaid web orders per IP scope.
    scope_hash = crypto.hmac_index(
        settings.privacy_key, crypto.PURPOSE_CLIENT_IP,
        merchant["id"], client_scope,
    )
    if await _open_order_count(merchant["id"], scope_hash) >= (
        MAX_OPEN_ORDERS_PER_SCOPE
    ):
        raise ProblemError(
            429, "rate-limited", "Rate Limited",
            "too many open orders — complete or wait for expiry",
        )

    resolved = await _resolve_items(merchant["id"], payload.get("items") or [])

    any_physical = any(
        e["product"]["format"] == "physical" for e in resolved
    )
    address = payload.get("address")
    if any_physical and not isinstance(address, dict):
        raise unprocessable(
            "invalid-shipping-destination", "Address required",
            "a structured address is required for physical items",
        )
    shipping_option = None
    if any_physical:
        d_tag = payload.get("shipping_option_d")
        if not d_tag:
            raise unprocessable(
                "invalid-shipping-destination", "Shipping required",
                "physical items require shipping_option_d",
            )
        shipping_option = await _resolve_shipping(
            merchant["id"], d_tag, address
        )
        _check_shipping_constraints(shipping_option, resolved)

    email = payload.get("email")
    email_opt_in = bool(payload.get("email_opt_in"))
    if email_opt_in and not email:
        raise unprocessable(
            "invalid-content", "email_opt_in requires email"
        )

    # Held-reservation row cap (§15) — checked before the claim tx; the
    # conditional stock guard remains the authoritative race arbiter.
    for entry in resolved:
        if await _held_reservation_count(
            entry["product"]["id"]
        ) >= MAX_HELD_PER_PRODUCT:
            raise unprocessable(
                "insufficient-stock", "Insufficient stock",
                "product is fully reserved",
            )

    # --- server-side totals (§3.4/§8.1 step 6) ---
    quotes: dict[str, fx.FxQuote] = {}
    components: list[int] = []
    line_rows: list[dict] = []
    subtotal_sat = 0
    for entry in resolved:
        p = entry["product"]
        currency = p["currency"] or "SAT"
        if currency not in quotes:
            try:
                quotes[currency] = (
                    fx.sat_quote() if currency == "SAT"
                    else await fx.quote_currency(currency)
                )
            except fx.FxRejection as exc:
                raise unprocessable(
                    "fx-unavailable", "Price conversion unavailable",
                    f"cannot price {currency}: {exc}",
                ) from exc
        quote = quotes[currency]
        unit_minor = p["amount_minor"] or 0
        line_minor = unit_minor * entry["qty"]
        try:
            line_sat = fx.convert_line(
                quote, currency=currency, amount_minor=line_minor,
                currency_decimals=p["currency_decimals"] or 0, now=now,
            )
        except fx.FxRejection as exc:
            raise unprocessable(
                "fx-unavailable", "Price conversion unavailable",
                str(exc),
            ) from exc
        components.append(line_sat)
        subtotal_sat += line_sat
        line_rows.append(
            {"product": p, "qty": entry["qty"], "unit_minor": unit_minor,
             "currency": currency,
             "decimals": p["currency_decimals"] or 0,
             "line_sat": line_sat}
        )
    shipping_sat = 0
    if shipping_option is not None:
        shipping_minor = (shipping_option["base_price_minor"] or 0)
        cur = shipping_option["currency"] or "SAT"
        if cur not in quotes:
            try:
                quotes[cur] = (
                    fx.sat_quote() if cur == "SAT"
                    else await fx.quote_currency(cur)
                )
            except fx.FxRejection as exc:
                raise unprocessable(
                    "fx-unavailable", "Price conversion unavailable",
                    f"cannot price {cur}: {exc}",
                ) from exc
        quote = quotes[cur]
        try:
            shipping_sat = fx.convert_line(
                quote, currency=cur, amount_minor=shipping_minor,
                currency_decimals=0, now=now,
            )
        except fx.FxRejection as exc:
            raise unprocessable(
                "fx-unavailable", "Price conversion unavailable",
                str(exc),
            ) from exc
        components.append(shipping_sat)
    try:
        total_sat = fx.checked_total_sat(components)
    except fx.FxRejection as exc:
        raise unprocessable(
            "invalid-total", "Invalid order total", str(exc),
        ) from exc

    order_id = uuid.uuid4().hex
    token = crypto.generate_public_token()
    external_id = uuid.uuid4().hex  # generated UUID for web (§3.3)
    await _insert_order_intake(
        merchant=merchant, resolved=line_rows,
        shipping_option=shipping_option, address=address,
        email=email, phone=payload.get("phone"),
        email_opt_in=email_opt_in, quotes=quotes,
        subtotal_sat=subtotal_sat, shipping_sat=shipping_sat,
        total_sat=total_sat, order_id=order_id,
        external_id=external_id, token=token,
        buyer_amount_sat=(
            max(0, int(payload["buyer_amount"]))
            if payload.get("buyer_amount") is not None else None
        ),
        client_scope=client_scope, settings=settings, now=now,
    )

    result = await begin_saga(order_id=order_id, settings=settings, now=now)
    state = result.get("state", "awaiting_payment")
    response = {
        "public_token": token,
        "order": {
            "state": state,
            "total_sat": total_sat,
            "bolt11": result.get("bolt11"),
            "expires_at": result.get("expires_at"),
        },
    }
    return {"_order_id": order_id, "response": response}


async def _insert_order_intake(
    *,
    merchant: dict,
    resolved: list[dict],
    shipping_option: dict | None,
    address: dict | None,
    email: str | None,
    phone: str | None,
    email_opt_in: bool,
    quotes: dict[str, fx.FxQuote],
    subtotal_sat: int,
    shipping_sat: int,
    total_sat: int,
    order_id: str,
    external_id: str,
    token: str,
    buyer_amount_sat: int | None,
    client_scope: str,
    settings: ExtSettings,
    now: int,
) -> None:
    """§8.1 step 8: orders(received) + items + fx + audit + token, one tx."""
    key = settings.master_keys[settings.active_key_version]
    ver = settings.active_key_version

    def _enc(plaintext: bytes, column: str) -> bytes:
        return crypto.encrypt(
            plaintext, key, record_id=order_id, table="orders",
            column=column, key_version=ver,
        )

    contact = json.dumps(
        {"email": email, "phone": phone}, separators=(",", ":")
    )
    token_enc = _enc(token.encode(), "public_token_enc")
    scope_hash = crypto.hmac_index(
        settings.privacy_key, crypto.PURPOSE_CLIENT_IP,
        merchant["id"], client_scope,
    )
    shipping_state = (
        "pending" if shipping_option is not None else "not_required"
    )
    async with DomainTransaction() as tx:
        await tx.execute(
            f"INSERT INTO {tx.table('orders')} "
            "(id, merchant_id, protocol, external_id_enc, external_id_hash,"
            " request_hash, currency, subtotal_sat, shipping_sat, total_sat,"
            " buyer_amount_sat,"
            " state, shipping_state, contact_enc, address_enc,"
            " shipping_option_id, public_token_hash, public_token_enc,"
            " public_token_expires_at, checkout_scope_hash, email_opt_in,"
            " created_at, updated_at) "
            "VALUES (:i, :m, 'web', :eie, :eih, :rh, 'SAT', :ss, :shs, :ts,"
            " :ba,"
            " 'received', :shst, :ce, :ae, :so, :pth, :pte, :ptx, :csh, :eoi,"
            " :n, :n)",
            {
                "i": order_id,
                "m": merchant["id"],
                "eie": _enc(external_id.encode(), "external_id_enc"),
                "eih": crypto.hmac_index(
                    settings.privacy_key, crypto.PURPOSE_ORDER_ID,
                    merchant["id"], crypto.normalize(external_id),
                ),
                "rh": None,
                "ba": buyer_amount_sat,
                "ss": subtotal_sat,
                "shs": shipping_sat,
                "ts": total_sat,
                "shst": shipping_state,
                "ce": _enc(contact.encode(), "contact_enc"),
                "ae": (
                    _enc(json.dumps(address).encode(), "address_enc")
                    if address is not None else None
                ),
                "so": shipping_option["id"] if shipping_option else None,
                "pth": crypto.token_lookup_hash(token),
                "pte": token_enc,
                "ptx": now + TOKEN_TTL_S,
                "csh": scope_hash,
                "eoi": email_opt_in,
                "n": now,
            },
        )
        for line in resolved:
            p = line["product"]
            await tx.execute(
                f"INSERT INTO {tx.table('order_items')} "
                "(id, order_id, product_id, product_d, title, quantity,"
                " unit_price_minor, currency, currency_decimals,"
                " line_total_sat) "
                "VALUES (:i, :o, :p, :pd, :t, :q, :up, :c, :cd, :ls)",
                {
                    "i": uuid.uuid4().hex,
                    "o": order_id,
                    "p": p["id"],
                    "pd": p["d_tag"],
                    "t": p["title"],
                    "q": line["qty"],
                    "up": line["unit_minor"],
                    "c": line["currency"],
                    "cd": line["decimals"],
                    "ls": line["line_sat"],
                },
            )
        for quote in quotes.values():
            if quote.source == "identity":
                continue  # same-currency orders persist no fx quote row
            await fx.persist_quote(tx, order_id, quote)
        await tx.execute(
            f"INSERT INTO {tx.table('order_events')} "
            "(id, order_id, from_state, to_state, actor, detail_json,"
            " created_at) "
            "VALUES (:i, :o, NULL, 'received', 'buyer', NULL, :n)",
            {"i": uuid.uuid4().hex, "o": order_id, "n": now},
        )
        # §8.8 order_received — merchant alerts only (customer sends omit
        # order_received; placed+paid is one combined event).
        notify_emails = json.loads(merchant["notify_emails"]) if (
            merchant["notify_emails"]
        ) else []
        notify_events = json.loads(merchant["notify_events"]) if (
            merchant["notify_events"]
        ) else {}
        order_stub = {
            "id": order_id, "merchant_id": merchant["id"],
            "email_opt_in": email_opt_in,
        }
        await order_service.enqueue_email_intents(
            tx, order=order_stub, event_type="order_received",
            merchant_notify_emails=notify_emails,
            merchant_notify_events=notify_events,
            customer_email=None, now=now,
        )


# --- section 8.2 saga --------------------------------------------------------


def core_external_id(order_id: str) -> str:
    """The deterministic recovery key (§4.8)."""
    return f"gammamarkets:{order_id}"


def decrypt_merchant_wallet(merchant: dict, settings: ExtSettings) -> str:
    """Decrypt the merchant's wallet_id_enc (record_id = merchant id)."""
    ver = crypto.envelope_version(merchant["wallet_id_enc"])
    raw = crypto.decrypt(
        merchant["wallet_id_enc"], settings.master_keys[ver],
        record_id=merchant["id"], table="merchants",
        column="wallet_id_enc", key_version=ver,
    )
    return raw.decode()


async def begin_saga(
    *, order_id: str, settings: ExtSettings | None = None,
    now: int | None = None,
) -> dict:
    """§8.2 steps 1–3: claim tx -> create_invoice -> attach tx.

    Idempotent by construction: the received->invoice_pending CAS means a
    second begin on a resumed order is a no-op SagaConflict; the caller
    (reconciliation) treats that as already-begun.
    """
    settings = settings or ext_settings()
    now = _now() if now is None else now
    async with db.connect() as conn:
        order = await conn.fetchone(
            f"SELECT * FROM {table('orders')} WHERE id = :i", {"i": order_id}
        )
        items = await conn.fetchall(
            f"SELECT product_id, quantity FROM {table('order_items')} "
            "WHERE order_id = :o",
            {"o": order_id},
        )
        merchant = await conn.fetchone(
            f"SELECT * FROM {table('merchants')} WHERE id = :m",
            {"m": order["merchant_id"]},
        )
    order, items, merchant = dict(order), [dict(r) for r in items], dict(merchant)

    wallet_id = decrypt_merchant_wallet(merchant, settings)
    ext_id = core_external_id(order_id)
    expires_at = now + settings.reservation_ttl

    # Step 1: conditional claim + CAS + held reservations + projection.
    async with DomainTransaction() as tx:
        for item in sorted(items, key=lambda i: i["product_id"]):
            rc = await tx.execute(
                f"UPDATE {tx.table('products')}"
                " SET stock_reserved = stock_reserved + :q"
                " WHERE id = :p AND deleted_at IS NULL"
                " AND (stock_on_hand IS NULL"
                " OR stock_on_hand - stock_reserved >= :q)",
                {"q": item["quantity"], "p": item["product_id"]},
            )
            if rc != 1:
                raise unprocessable(
                    "insufficient-stock", "Insufficient stock",
                    "requested quantity is not available",
                )
        await order_service.transition_order(
            tx, order_id=order_id, from_state="received",
            to_state="invoice_pending", actor="system", now=now,
        )
        for item in items:
            await tx.execute(
                f"INSERT INTO {tx.table('inventory_reservations')} "
                "(id, product_id, order_id, quantity, state, expires_at,"
                " created_at, updated_at) "
                "VALUES (:i, :p, :o, :q, 'held', :e, :n, :n)",
                {
                    "i": uuid.uuid4().hex,
                    "p": item["product_id"],
                    "o": order_id,
                    "q": item["quantity"],
                    "e": expires_at,
                    "n": now,
                },
            )
        await tx.execute(
            f"INSERT INTO {tx.table('payments')} "
            "(id, order_id, core_external_id, wallet_refs_enc,"
            " wallet_id_hash, source_wallet_id_hash, amount_sat, status,"
            " created_at) "
            "VALUES (:i, :o, :e, :wre, :wh, :swh, :a, 'creating', :n)",
            {
                "i": uuid.uuid4().hex,
                "o": order_id,
                "e": ext_id,
                "wre": crypto.encrypt(
                    f"{wallet_id}|{wallet_id}".encode(),
                    settings.master_keys[settings.active_key_version],
                    record_id=order_id, table="payments",
                    column="wallet_refs_enc",
                    key_version=settings.active_key_version,
                ),
                "wh": crypto.hmac_index(
                    settings.privacy_key, crypto.PURPOSE_WALLET_ID,
                    merchant["id"], crypto.normalize(wallet_id),
                ),
                "swh": crypto.hmac_index(
                    settings.privacy_key, crypto.PURPOSE_SOURCE_WALLET_ID,
                    merchant["id"], crypto.normalize(wallet_id),
                ),
                "a": order["total_sat"],
                "n": now,
            },
        )

    # Step 2: the external call — outside any transaction.
    from lnbits.core.services.payments import InvoiceError, create_invoice

    try:
        payment = await create_invoice(
            wallet_id=wallet_id,
            amount=order["total_sat"],
            currency="sat",
            memo=INVOICE_MEMO,
            expiry=settings.reservation_ttl,
            extension="gammamarkets",
            external_id=ext_id,
            extra={"tag": "gammamarkets", "order_id": order_id},
        )
    except InvoiceError as exc:
        if exc.status == "failed":
            await _mark_rejection(order_id, now=_now())
            return {"order_id": order_id, "state": "rejected"}
        await _mark_unknown(order_id, now=_now())
        return {"order_id": order_id, "state": "invoice_pending"}
    except Exception:
        # Timeouts/network/unknown outcomes — never a second invoice.
        await _mark_unknown(order_id, now=_now())
        return {"order_id": order_id, "state": "invoice_pending"}

    # Step 3: attach.
    return await attach_payment(order_id=order_id, payment=payment, now=_now())


async def attach_payment(*, order_id: str, payment, now: int) -> dict:
    """§8.2 step 3: persist the invoice to the projection regardless of
    commerce state; enter awaiting_payment only for invoice_pending."""
    from bolt11 import decode as bolt11_decode

    settings = ext_settings()
    key = settings.master_keys[settings.active_key_version]
    ver = settings.active_key_version

    invoice = bolt11_decode(payment.bolt11)
    expiry_dt = payment.expiry or getattr(invoice, "expiry_date", None)
    expiry_epoch = int(expiry_dt.timestamp()) if expiry_dt else None

    def _enc(plaintext: bytes, column: str) -> bytes:
        return crypto.encrypt(
            plaintext, key, record_id=order_id, table="payments",
            column=column, key_version=ver,
        )

    wallet_refs = f"{payment.wallet_id}|{payment.wallet_id}"
    async with DomainTransaction() as tx:
        order = await tx.fetch_one(
            f"SELECT * FROM {tx.table('orders')} WHERE id = :i",
            {"i": order_id},
        )
        if not order:
            raise order_service.TransitionConflict(
                f"order {order_id!r} does not exist"
            )
        rc = await tx.execute(
            f"UPDATE {tx.table('payments')} "
            "SET payment_hash = :ph, checking_id_enc = :ci,"
            " bolt11_enc = :b11, wallet_refs_enc = :wr, status = 'pending'"
            " WHERE order_id = :o AND core_external_id = :e",
            {
                "ph": payment.payment_hash,
                "ci": _enc(payment.checking_id.encode(), "checking_id_enc"),
                "b11": _enc(payment.bolt11.encode(), "bolt11_enc"),
                "wr": _enc(wallet_refs.encode(), "wallet_refs_enc"),
                "o": order_id,
                "e": core_external_id(order_id),
            },
        )
        if rc != 1:
            raise order_service.TransitionConflict(
                f"attach failed: no creating projection for {order_id!r}"
            )
        await tx.execute(
            f"UPDATE {tx.table('orders')} "
            "SET payment_hash = :ph, invoice_expiry = :ie, updated_at = :n"
            " WHERE id = :i",
            {
                "ph": payment.payment_hash,
                "ie": expiry_epoch,
                "n": now,
                "i": order_id,
            },
        )
        if order["state"] == "invoice_pending":
            if expiry_epoch:
                await tx.execute(
                    f"UPDATE {tx.table('inventory_reservations')}"
                    " SET expires_at = :e, updated_at = :n"
                    " WHERE order_id = :o AND state = 'held'",
                    {"e": expiry_epoch, "n": now, "o": order_id},
                )
            await order_service.transition_order(
                tx, order_id=order_id, from_state="invoice_pending",
                to_state="awaiting_payment", actor="system",
                detail={"payment_hash": payment.payment_hash}, now=now,
            )
            return {
                "order_id": order_id, "state": "awaiting_payment",
                "bolt11": payment.bolt11, "expires_at": expiry_epoch,
            }
        # Cancelled or other state: keep the projection for late-settlement
        # detection; never deliver BOLT11.
        return {
            "order_id": order_id, "state": order["state"],
            "bolt11": None, "expires_at": expiry_epoch,
        }


async def _mark_rejection(order_id: str, *, now: int) -> None:
    """Definitive rejection: projection failed; release/reject only an
    invoice_pending order (§8.2 step 4)."""
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('payments')} SET status = 'failed'"
            " WHERE order_id = :o"
            " AND status IN ('creating', 'creation_unknown')",
            {"o": order_id},
        )
        order = await tx.fetch_one(
            f"SELECT state FROM {tx.table('orders')} WHERE id = :i",
            {"i": order_id},
        )
        if order and order["state"] == "invoice_pending":
            await order_service.transition_order(
                tx, order_id=order_id, from_state="invoice_pending",
                to_state="rejected", actor="system",
                reason="invoice-creation-rejected", now=now,
            )
            await order_service.release_reservations(
                tx, order_id=order_id, to_state="released", now=now
            )


async def _mark_unknown(order_id: str, *, now: int) -> None:
    """Timeout/unknown: status=creation_unknown + payment_exception — never
    a second invoice; reconciliation recovers by exact external id."""
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('payments')} SET status = 'creation_unknown'"
            " WHERE order_id = :o AND status = 'creating'",
            {"o": order_id},
        )
        await tx.execute(
            f"UPDATE {tx.table('orders')} "
            "SET payment_exception = TRUE,"
            " payment_exception_reason = 'invoice-creation-unknown',"
            " updated_at = :n WHERE id = :i",
            {"n": now, "i": order_id},
        )


async def _resume_order(record: dict, *, now: int) -> dict:
    """Resume a crashed-lease order through the saga (§4.15).

    The order row exists, so a same-body retry rebuilds the original 201
    from the durable projection: the AEAD ``public_token_enc`` copy (kept
    while the token is live) and the persisted ``bolt11_enc``. A still-
    ``received`` order resumes the saga idempotently first.
    """
    order_id = record["_resume_order_id"]
    settings = ext_settings()
    order = await order_service.get_order(order_id)
    if order["state"] == "received":
        await begin_saga(order_id=order_id, now=now)
        order = await order_service.get_order(order_id)

    ver = crypto.envelope_version(order["public_token_enc"])
    token = crypto.decrypt(
        order["public_token_enc"], settings.master_keys[ver],
        record_id=order_id, table="orders", column="public_token_enc",
        key_version=ver,
    ).decode()
    bolt11 = None
    async with db.connect() as conn:
        payment = await conn.fetchone(
            f"SELECT bolt11_enc FROM {table('payments')} WHERE order_id = :o",
            {"o": order_id},
        )
    if payment and payment["bolt11_enc"] is not None:
        bver = crypto.envelope_version(payment["bolt11_enc"])
        bolt11 = crypto.decrypt(
            payment["bolt11_enc"], settings.master_keys[bver],
            record_id=order_id, table="payments", column="bolt11_enc",
            key_version=bver,
        ).decode()
    return {
        "public_token": token,
        "order": {
            "state": order["state"],
            "total_sat": order["total_sat"],
            "bolt11": bolt11 if order["state"] == "awaiting_payment" else None,
            "expires_at": order["invoice_expiry"],
        },
    }
