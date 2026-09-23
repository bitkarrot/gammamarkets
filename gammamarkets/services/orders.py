"""Order domain — spec sections 7.1–7.3, 8.3 admin actions, 8.8 intents.

``transition_order`` is the ONLY sanctioned way to change ``orders.state``:
legality check -> compare-and-swap (``WHERE state = :from_state``) -> the
``order_events`` audit row, all inside the caller's domain transaction. The
transition table is kept LITERAL against ``harness.state`` — a runtime test
asserts parity rather than re-deriving it.

Every mutation path also enqueues the matching §8.8 email intent in the
same transaction through ``enqueue_email_intents`` so dedupe rules apply
uniformly.
"""

from __future__ import annotations

import json
import time
import uuid

from ..db import DomainTransaction
from ..security import not_found, unprocessable


class IllegalTransition(Exception):
    """The requested transition is not in the section 7.1 table."""


class TransitionConflict(Exception):
    """The compare-and-swap lost (the order was not in the expected state)."""


# --- Section 7.1 order state machine (literal — kept identical to
# --- harness/state.py; a runtime test asserts the tables match) -----------

ORDER_STATES = (
    "received",
    "invoice_pending",
    "awaiting_payment",
    "confirmed",
    "processing",
    "completed",
    "rejected",
    "expired",
    "cancelled",
)

ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    "received": frozenset({"rejected", "invoice_pending", "cancelled"}),
    "invoice_pending": frozenset({"awaiting_payment", "rejected", "cancelled"}),
    "awaiting_payment": frozenset({"confirmed", "expired", "cancelled"}),
    "confirmed": frozenset({"processing", "cancelled"}),
    "processing": frozenset({"completed", "cancelled"}),
    "expired": frozenset({"confirmed"}),
    "cancelled": frozenset({"confirmed"}),
    "completed": frozenset(),
    "rejected": frozenset(),
}

ORDER_TERMINAL_STATES = ("completed", "rejected")

REASON_REQUIRED_TRANSITIONS = frozenset(
    {
        ("confirmed", "cancelled"),
        ("expired", "confirmed"),
        ("cancelled", "confirmed"),
    }
)

BUYER_CANCELLABLE_STATES = ("received", "invoice_pending", "awaiting_payment")

# --- Section 7.2 shipping state machine (literal) -------------------------

SHIPPING_STATES = (
    "not_required",
    "pending",
    "processing",
    "shipped",
    "delivered",
    "exception",
)

SHIPPING_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_required": frozenset({"pending"}),
    "pending": frozenset({"processing"}),
    "processing": frozenset({"shipped", "exception"}),
    "shipped": frozenset({"delivered", "exception"}),
    "exception": frozenset({"processing", "shipped"}),
    "delivered": frozenset(),
}

# --- Section 7.3 reservation state machine (literal) ----------------------

RESERVATION_STATES = ("held", "consumed", "released", "expired")

RESERVATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "held": frozenset({"consumed", "released", "expired"}),
    "consumed": frozenset(),
    "released": frozenset(),
    "expired": frozenset(),
}

# --- Section 8.8 email event types ------------------------------------------

EMAIL_EVENT_TYPES = (
    "order_received",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "expired",
    "on_hold",
    "refund_requested",
)

#: order-state -> customer-facing event type for admin/system transitions.
_STATE_EMAIL_EVENTS = {
    "confirmed": "confirmed",
    "processing": "processing",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "expired": "expired",
}


def _now() -> int:
    return int(time.time())


# --- transition_order (section 7.1 single entry path) ------------------------


async def transition_order(
    tx: DomainTransaction,
    *,
    order_id: str,
    to_state: str,
    from_state: str | None = None,
    actor: str = "system",
    reason: str | None = None,
    detail: dict | None = None,
    now: int | None = None,
) -> str:
    """Transition one order through the section 7.1 machine.

    Runs inside the caller's open domain transaction. Raises
    ``IllegalTransition`` for a transition outside the table (or a missing
    required reason) and ``TransitionConflict`` when the CAS loses.
    Returns the effective from-state.
    """
    now = _now() if now is None else now
    orders = tx.table("orders")

    if from_state is None:
        row = await tx.fetch_one(
            f"SELECT state FROM {orders} WHERE id = :i", {"i": order_id}
        )
        if not row:
            raise TransitionConflict(f"order {order_id!r} does not exist")
        from_state = row["state"]

    if to_state not in ORDER_TRANSITIONS.get(from_state, frozenset()):
        raise IllegalTransition(
            f"illegal order transition {from_state!r} -> {to_state!r}"
        )
    if (from_state, to_state) in REASON_REQUIRED_TRANSITIONS and not reason:
        raise IllegalTransition(
            f"transition {from_state!r} -> {to_state!r} requires a reason"
        )

    rc = await tx.execute(
        f"UPDATE {orders} SET state = :to WHERE id = :i AND state = :f",
        {"to": to_state, "i": order_id, "f": from_state},
    )
    if rc != 1:
        raise TransitionConflict(
            f"order CAS lost for {order_id!r}"
            f" (expected {from_state!r}, target {to_state!r})"
        )
    await tx.execute(
        f"UPDATE {orders} SET updated_at = :n WHERE id = :i",
        {"n": now, "i": order_id},
    )
    payload: dict = {}
    if reason is not None:
        payload["reason"] = reason
    if detail:
        payload.update(detail)
    await tx.execute(
        f"INSERT INTO {tx.table('order_events')} "
        "(id, order_id, from_state, to_state, actor, detail_json, created_at)"
        " VALUES (:i, :o, :f, :t, :a, :d, :n)",
        {
            "i": uuid.uuid4().hex,
            "o": order_id,
            "f": from_state,
            "t": to_state,
            "a": actor,
            "d": json.dumps(payload) if payload else None,
            "n": now,
        },
    )
    return from_state


# --- shared helpers -------------------------------------------------------


async def get_order(order_id: str, merchant_id: str | None = None) -> dict:
    """Fetch one order (merchant-scoped when merchant_id is given)."""
    from ..db import db, table

    async with db.connect() as conn:
        if merchant_id is None:
            row = await conn.fetchone(
                f"SELECT * FROM {table('orders')} WHERE id = :i",
                {"i": order_id},
            )
        else:
            row = await conn.fetchone(
                f"SELECT * FROM {table('orders')} "
                "WHERE id = :i AND merchant_id = :m",
                {"i": order_id, "m": merchant_id},
            )
    if not row:
        raise not_found("order not found")
    return dict(row)


async def release_reservations(
    tx: DomainTransaction, *, order_id: str, to_state: str, now: int
) -> int:
    """Release held reservations exactly once, decrementing stock_reserved.

    Only rows still in state ``held`` flip; the stock decrement is bound to
    that flip in the same transaction, so a second pass is a no-op.
    """
    released = 0
    held = await tx.fetch_all(
        f"SELECT id, product_id, quantity FROM"
        f" {tx.table('inventory_reservations')}"
        " WHERE order_id = :o AND state = 'held'",
        {"o": order_id},
    )
    for row in held:
        rc = await tx.execute(
            f"UPDATE {tx.table('inventory_reservations')}"
            " SET state = :s, updated_at = :n"
            " WHERE id = :i AND state = 'held'",
            {"s": to_state, "n": now, "i": row["id"]},
        )
        if rc != 1:
            raise TransitionConflict(
                f"reservation CAS lost for {row['id']}"
            )
        await tx.execute(
            f"UPDATE {tx.table('products')}"
            " SET stock_reserved = stock_reserved - :q, updated_at = :n"
            " WHERE id = :p",
            {"q": row["quantity"], "n": now, "p": row["product_id"]},
        )
        released += row["quantity"]
    return released


# --- section 8.8 email intents (shared by every mutation path) --------------

#: Which notify_events keys gate merchant-channel rows (merchant config).
_MERCHANT_EVENT_KEYS = {
    "order_received": "order_received",
    "confirmed": "confirmed",
    "processing": "processing",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "expired": "expired",
    "on_hold": "on_hold",
    "refund_requested": "refund_requested",
}

#: Customer sends are strictly opt-in per order (orders.email_opt_in) AND
#: transactional-only — order_received is never sent to the customer
#: (placed + paid arrive as one combined ``confirmed`` email, §8.8).
_CUSTOMER_EVENTS = frozenset(set(EMAIL_EVENT_TYPES) - {"order_received"})


async def enqueue_email_intents(
    tx: DomainTransaction,
    *,
    order: dict,
    event_type: str,
    merchant_notify_emails: list[str],
    merchant_notify_events: dict,
    customer_email: str | None,
    now: int | None = None,
) -> int:
    """Enqueue §8.8 per-recipient rows for one order event, in-tx.

    Merchant rows: one per configured notify_emails address, gated by the
    merchant's notify_events flags (default ON when unconfigured). Customer
    row: only when the order's email_opt_in is true, an address exists, and
    the event is a customer-facing type. ``UNIQUE(order_id, channel,
    event_type, recipient_hash)`` dedupes via ON CONFLICT DO NOTHING.
    Returns the number of rows inserted.
    """
    from ..crypto import encrypt, hmac_index, normalize
    from ..settings import ext_settings

    if event_type not in EMAIL_EVENT_TYPES:
        raise unprocessable(
            "invalid-transition", f"unknown email event {event_type!r}"
        )
    now = _now() if now is None else now
    settings = ext_settings()
    key = settings.master_keys[settings.active_key_version]
    ver = settings.active_key_version
    inserted = 0

    async def _insert(recipient: str, channel: str) -> bool:
        enc = encrypt(
            recipient.encode(), key,
            record_id=order["id"], table="email_queue",
            column="recipient_enc", key_version=ver,
        )
        digest = hmac_index(
            settings.privacy_key, "email-recipient",
            order["merchant_id"], normalize(recipient),
        )
        rc = await tx.execute(
            f"INSERT INTO {tx.table('email_queue')} "
            "(id, merchant_id, order_id, channel, event_type,"
            " recipient_enc, recipient_hash, state, attempts,"
            " next_attempt_at, claim_token, created_at) "
            "VALUES (:i, :m, :o, :c, :e, :re, :rh, 'pending', 0, :n,"
            " 0, :n) ON CONFLICT DO NOTHING",
            {
                "i": uuid.uuid4().hex,
                "m": order["merchant_id"],
                "o": order["id"],
                "c": channel,
                "e": event_type,
                "re": enc,
                "rh": digest,
                "n": now,
            },
        )
        return rc == 1

    # Merchant channel — notify_events flags default ON per event.
    flag = _MERCHANT_EVENT_KEYS[event_type]
    if merchant_notify_events.get(flag, True):
        for addr in merchant_notify_emails:
            if await _insert(addr, "merchant"):
                inserted += 1

    # Customer channel — strictly per-order opt-in.
    if (
        event_type in _CUSTOMER_EVENTS
        and order.get("email_opt_in")
        and customer_email
    ):
        if await _insert(customer_email, "customer"):
            inserted += 1

    return inserted


# --- section 8.1 step 4 cancellation (shared by admin + settlement paths) ----


async def cancel_order(
    *,
    order_id: str,
    actor: str,
    reason: str | None,
    merchant_context: dict | None = None,
) -> dict:
    """Cancellation releases held stock exactly once (§7.1/§8.2 step 4).

    All cancels in Release A are merchant-initiated (there is no public
    cancel route); §7.1 legality governs — confirmed->cancelled requires a
    reason, terminal states reject. An already-cancelled order is a no-op
    that releases nothing.
    """
    now = _now()
    async with DomainTransaction() as tx:
        order = await _order_row(tx, order_id)
        if order["state"] == "cancelled":
            return {"order_id": order_id, "action": "no-op-already-cancelled"}
        await transition_order(
            tx, order_id=order_id, from_state=order["state"],
            to_state="cancelled", actor=actor, reason=reason, now=now,
        )
        released = await release_reservations(
            tx, order_id=order_id, to_state="released", now=now
        )
        if merchant_context is not None:
            await enqueue_email_intents(
                tx, order=order, event_type="cancelled",
                merchant_notify_emails=merchant_context["notify_emails"],
                merchant_notify_events=merchant_context["notify_events"],
                customer_email=merchant_context.get("customer_email"),
                now=now,
            )
        return {
            "order_id": order_id,
            "action": "cancelled",
            "released": released,
        }


async def _order_row(tx: DomainTransaction, order_id: str) -> dict:
    row = await tx.fetch_one(
        f"SELECT * FROM {tx.table('orders')} WHERE id = :i", {"i": order_id}
    )
    if not row:
        raise not_found("order not found")
    return dict(row)


# --- section 5.3 admin order actions -------------------------------------------

_MERCHANT_NOTIFY_SQL = (
    "SELECT notify_emails, notify_events FROM {m} WHERE id = :mid"
)


async def _merchant_notify(merchant_id: str) -> tuple[list[str], dict]:
    from ..db import db, table

    async with db.connect() as conn:
        row = await conn.fetchone(
            _MERCHANT_NOTIFY_SQL.format(m=table("merchants")),
            {"mid": merchant_id},
        )
    emails = json.loads(row["notify_emails"]) if (
        row and row["notify_emails"]
    ) else []
    events = json.loads(row["notify_events"]) if (
        row and row["notify_events"]
    ) else {}
    return emails, events


async def _customer_email(order: dict) -> str | None:
    from .. import crypto
    from ..settings import ext_settings

    if not order.get("contact_enc"):
        return None
    settings = ext_settings()
    try:
        ver = crypto.envelope_version(order["contact_enc"])
        contact = json.loads(
            crypto.decrypt(
                order["contact_enc"], settings.master_keys[ver],
                record_id=order["id"], table="orders",
                column="contact_enc", key_version=ver,
            )
        )
        return contact.get("email")
    except Exception:
        return None


async def _notify_ctx(order: dict) -> dict:
    emails, events = await _merchant_notify(order["merchant_id"])
    return {
        "notify_emails": emails,
        "notify_events": events,
        "customer_email": await _customer_email(order),
    }


async def list_orders(
    merchant_id: str, user, *, state: str | None = None,
    protocol: str | None = None, q: str | None = None,
) -> list[dict]:
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    from ..db import db, table

    clauses = ["merchant_id = :m"]
    params: dict = {"m": merchant_id}
    if state:
        # The UI-SPEC filter set adds "needs_attention" (payment exception
        # or oversold) on top of the §7.1 states.
        if state == "needs_attention":
            clauses.append("(payment_exception OR oversold)")
        elif state not in ORDER_STATES:
            raise unprocessable("invalid-transition", "Unknown state")
        else:
            clauses.append("state = :s")
            params["s"] = state
    if protocol:
        if protocol not in ("web", "gamma", "nip15"):
            raise unprocessable("invalid-transition", "Unknown protocol")
        clauses.append("protocol = :p")
        params["p"] = protocol
    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT id, protocol, state, shipping_state, total_sat,"
            " payment_exception, oversold, email_opt_in, created_at,"
            " updated_at, contact_enc FROM "
            f"{table('orders')} WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at DESC LIMIT 200",
            params,
        )
        order_ids = [r["id"] for r in rows]
        item_rows: dict[str, list] = {}
        if order_ids:
            marks = ",".join(f"'{i}'" for i in order_ids)
            for it in await conn.fetchall(
                f"SELECT order_id, title, quantity FROM"
                f" {table('order_items')} WHERE order_id IN ({marks})"
                " ORDER BY id"
            ):
                item_rows.setdefault(it["order_id"], []).append(dict(it))
    out = []
    for r in rows:
        row = dict(r)
        items = item_rows.get(row["id"], [])
        row["item_count"] = len(items)
        row["first_item"] = items[0]["title"] if items else None
        row["first_item_qty"] = items[0]["quantity"] if items else None
        row["buyer"] = _buyer_handle(row)
        row.pop("contact_enc", None)
        out.append(row)
    if q:
        # "Search order or buyer": id-prefix OR decrypted-handle substring —
        # contact_enc can't match in SQL, so the buyer arm filters here.
        needle = q.strip().lower()
        out = [
            r for r in out
            if r["id"].lower().startswith(needle)
            or (r["buyer"] or "").lower().find(needle) >= 0
        ]
    return out


def _buyer_handle(order: dict) -> str | None:
    """List-row buyer handle (UI-SPEC §B1): web orders show the supplied
    email; protocol orders show the buyer npub — decrypted owner-side."""
    enc = order.get("contact_enc")
    if enc is None:
        return None
    from .. import crypto
    from ..settings import ext_settings

    settings = ext_settings()
    try:
        ver = crypto.envelope_version(enc)
        raw = crypto.decrypt(
            enc, settings.master_keys[ver],
            record_id=order["id"], table="orders", column="contact_enc",
            key_version=ver,
        ).decode()
        contact = json.loads(raw)
    except Exception:
        return None
    return contact.get("email") or contact.get("npub")


async def order_detail(merchant_id: str, user, order_id: str) -> dict:
    """Full detail — decrypted contact/address for the OWNER only."""
    from .. import crypto
    from ..settings import ext_settings
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    order = await get_order(order_id, merchant_id)
    settings = ext_settings()

    def _dec(envelope: bytes | None, column: str) -> str | None:
        if envelope is None:
            return None
        try:
            ver = crypto.envelope_version(envelope)
            return crypto.decrypt(
                envelope, settings.master_keys[ver],
                record_id=order_id, table="orders", column=column,
                key_version=ver,
            ).decode()
        except Exception:
            return None

    async with DomainTransaction() as tx:
        items = await tx.fetch_all(
            f"SELECT product_id, product_d, title, quantity,"
            " unit_price_minor, currency, line_total_sat, backordered_qty"
            f" FROM {tx.table('order_items')} WHERE order_id = :o",
            {"o": order_id},
        )
        payment = await tx.fetch_one(
            f"SELECT status, amount_sat, settled_at, created_at"
            f" FROM {tx.table('payments')} WHERE order_id = :o",
            {"o": order_id},
        )
        fulfil = await tx.fetch_one(
            f"SELECT tracking_enc, carrier, eta, updated_at"
            f" FROM {tx.table('order_fulfillment')} WHERE order_id = :o",
            {"o": order_id},
        )
    tracking = None
    if fulfil and fulfil["tracking_enc"] is not None:
        try:
            ver = crypto.envelope_version(fulfil["tracking_enc"])
            tracking = crypto.decrypt(
                fulfil["tracking_enc"], settings.master_keys[ver],
                record_id=order_id, table="order_fulfillment",
                column="tracking_enc", key_version=ver,
            ).decode()
        except Exception:
            tracking = None
    contact = _dec(order.get("contact_enc"), "contact_enc")
    address = _dec(order.get("address_enc"), "address_enc")
    return {
        "id": order["id"],
        "protocol": order["protocol"],
        "state": order["state"],
        "shipping_state": order["shipping_state"],
        "currency": order["currency"],
        "subtotal_sat": order["subtotal_sat"],
        "shipping_sat": order["shipping_sat"],
        "total_sat": order["total_sat"],
        "buyer_amount_sat": order["buyer_amount_sat"],
        "payment_exception": bool(order["payment_exception"]),
        "payment_exception_reason": order["payment_exception_reason"],
        "payment_exception_resolution": (
            order["payment_exception_resolution"]
        ),
        "oversold": bool(order["oversold"]),
        "email_opt_in": bool(order["email_opt_in"]),
        "invoice_expiry": order["invoice_expiry"],
        "shipping_option_id": order["shipping_option_id"],
        "contact": json.loads(contact) if contact else None,
        "address": json.loads(address) if address else None,
        "items": [dict(i) for i in items],
        "payment": dict(payment) if payment else None,
        "fulfillment": (
            {"tracking": tracking, "carrier": fulfil["carrier"],
             "eta": fulfil["eta"], "updated_at": fulfil["updated_at"]}
            if fulfil else None
        ),
        "created_at": order["created_at"],
        "updated_at": order["updated_at"],
    }


async def admin_set_status(
    merchant_id: str, user, order_id: str, to_state: str,
) -> dict:
    """§5.3 status transition — §7.1 legality only; illegal ->
    ``invalid-transition``."""
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    now = _now()
    async with DomainTransaction() as tx:
        order = await _order_row(tx, order_id)
        if order["merchant_id"] != merchant_id:
            raise not_found("order not found")
        try:
            await transition_order(
                tx, order_id=order_id, from_state=order["state"],
                to_state=to_state, actor="merchant", now=now,
            )
        except IllegalTransition as exc:
            raise unprocessable(
                "invalid-transition", "Invalid transition", str(exc)
            ) from exc
        event = _STATE_EMAIL_EVENTS.get(to_state)
        if event:
            ctx = await _notify_ctx(order)
            await enqueue_email_intents(
                tx, order=order, event_type=event,
                merchant_notify_emails=ctx["notify_emails"],
                merchant_notify_events=ctx["notify_events"],
                customer_email=ctx["customer_email"], now=now,
            )
        return {"id": order_id, "state": to_state}


async def admin_set_shipping(
    merchant_id: str, user, order_id: str, *, shipping_state: str,
    tracking: str | None = None, carrier: str | None = None,
    eta: str | None = None,
) -> dict:
    """§5.3 shipping update — §7.2 transition; tracking_enc at rest."""
    from .. import crypto
    from ..settings import ext_settings
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    if shipping_state not in SHIPPING_STATES:
        raise unprocessable("invalid-transition", "Unknown shipping state")
    settings = ext_settings()
    now = _now()
    async with DomainTransaction() as tx:
        order = await _order_row(tx, order_id)
        if order["merchant_id"] != merchant_id:
            raise not_found("order not found")
        current = order["shipping_state"]
        if shipping_state not in SHIPPING_TRANSITIONS.get(
            current, frozenset()
        ):
            raise unprocessable(
                "invalid-transition", "Invalid transition",
                f"{current!r} -> {shipping_state!r} is not legal",
            )
        rc = await tx.execute(
            f"UPDATE {tx.table('orders')} SET shipping_state = :s,"
            " updated_at = :n WHERE id = :i AND shipping_state = :c",
            {"s": shipping_state, "n": now, "i": order_id, "c": current},
        )
        if rc != 1:
            raise unprocessable(
                "invalid-transition", "Invalid transition",
                "shipping state changed concurrently",
            )
        tracking_enc = None
        if tracking is not None:
            tracking_enc = crypto.encrypt(
                tracking.encode(),
                settings.master_keys[settings.active_key_version],
                record_id=order_id, table="order_fulfillment",
                column="tracking_enc",
                key_version=settings.active_key_version,
            )
        await tx.execute(
            f"INSERT INTO {tx.table('order_fulfillment')} "
            "(order_id, tracking_enc, carrier, eta, updated_at) "
            "VALUES (:o, :t, :c, :e, :n) "
            "ON CONFLICT (order_id) DO UPDATE SET"
            " tracking_enc = COALESCE(:t, order_fulfillment.tracking_enc),"
            " carrier = COALESCE(:c, order_fulfillment.carrier),"
            " eta = COALESCE(:e, order_fulfillment.eta),"
            " updated_at = :n",
            {"o": order_id, "t": tracking_enc, "c": carrier, "e": eta,
             "n": now},
        )
        event = _STATE_EMAIL_EVENTS.get(shipping_state)
        if event:
            ctx = await _notify_ctx(order)
            await enqueue_email_intents(
                tx, order=order, event_type=event,
                merchant_notify_emails=ctx["notify_emails"],
                merchant_notify_events=ctx["notify_events"],
                customer_email=ctx["customer_email"], now=now,
            )
        return {"id": order_id, "shipping_state": shipping_state}


async def admin_cancel(
    merchant_id: str, user, order_id: str, reason: str | None,
) -> dict:
    """§5.3 merchant-initiated cancel (reason required post-confirm)."""
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    order = await get_order(order_id, merchant_id)
    ctx = await _notify_ctx(order)
    try:
        return await cancel_order(
            order_id=order_id, actor="merchant", reason=reason,
            merchant_context=ctx,
        )
    except IllegalTransition as exc:
        raise unprocessable(
            "invalid-transition", "Invalid transition", str(exc)
        ) from exc


async def admin_resolve_exception(
    merchant_id: str, user, order_id: str, *, action: str,
    refund_reference: str | None = None,
) -> dict:
    from . import merchant as merchant_service
    from . import settlement

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    await get_order(order_id, merchant_id)
    return await settlement.resolve_exception(
        order_id=order_id, action=action,
        refund_reference=refund_reference,
    )


async def admin_reissue_token(
    merchant_id: str, user, order_id: str,
) -> dict:
    """§5.3 token reissue — old token revoked immediately (the lookup hash
    is replaced) and the AEAD copy rotated; the new link is returned once."""
    from .. import crypto
    from ..settings import ext_settings
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    settings = ext_settings()
    order = await get_order(order_id, merchant_id)
    if order["protocol"] != "web":
        raise unprocessable(
            "invalid-transition", "Not a web order",
            "public tokens apply to web orders only",
        )
    now = _now()
    token = crypto.generate_public_token()
    token_enc = crypto.encrypt(
        token.encode(), settings.master_keys[settings.active_key_version],
        record_id=order_id, table="orders", column="public_token_enc",
        key_version=settings.active_key_version,
    )
    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('orders')} SET public_token_hash = :h,"
            " public_token_enc = :e, public_token_expires_at = :x,"
            " updated_at = :n WHERE id = :i",
            {
                "h": crypto.token_lookup_hash(token),
                "e": token_enc,
                "x": now + 30 * 86400,
                "n": now,
                "i": order_id,
            },
        )
    return {
        "id": order_id,
        "public_token": token,
        "expires_at": now + 30 * 86400,
    }


async def order_events(merchant_id: str, user, order_id: str) -> list[dict]:
    from . import merchant as merchant_service

    await merchant_service.get_merchant_row(merchant_id, str(user.id))
    await get_order(order_id, merchant_id)
    from ..db import db, table

    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT from_state, to_state, actor, detail_json, created_at"
            f" FROM {table('order_events')} WHERE order_id = :o"
            " ORDER BY created_at ASC, id ASC",
            {"o": order_id},
        )
    return [
        {
            "from_state": r["from_state"],
            "to_state": r["to_state"],
            "actor": r["actor"],
            "detail": json.loads(r["detail_json"]) if r["detail_json"] else {},
            "created_at": r["created_at"],
        }
        for r in rows
    ]
