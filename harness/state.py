"""Section 7 state machines: the single ``transition_order()`` entry path
plus the section 7.2-7.5 enums as declarative golden tables (D-08).

Every table below is kept LITERAL against the specification text so plan
01-03's P0-14 closure gate can diff it against the specification registry.

- Section 7.1 order state: ``transition_order()`` is the ONLY sanctioned way
  to change ``orders.state``; it performs the legality check, the
  compare-and-swap (``WHERE state = :from_state``), and writes the
  ``order_events`` audit row in the SAME transaction. No model code path
  writes ``orders.state`` directly.
- Sections 7.2-7.5: declarative transition tables used by the queue, email,
  and saga models and diffed by the P0-14 closure gate.
"""

from __future__ import annotations

import json
import uuid

from harness import tx as tx_module


class IllegalTransition(Exception):
    """The requested transition is not in the section 7.1 table."""


class TransitionConflict(tx_module.SagaConflict):
    """The compare-and-swap lost (the order was not in the expected state).

    Subclasses ``SagaConflict``: a lost CAS is exactly the section 8.2
    "rowcount != 1 -> roll back the entire transaction" precondition.
    """


# --- Section 7.1: order state machine (literal) -------------------------------

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

#: received -> rejected | invoice_pending | cancelled
#: invoice_pending -> awaiting_payment | rejected | cancelled
#: awaiting_payment -> confirmed | expired | cancelled
#: confirmed -> processing | cancelled          (cancel after confirm: reason)
#: processing -> completed | cancelled
#: expired | cancelled -> confirmed              (merchant-only late-settlement
#:                                                accept: reason required)
#: completed, rejected -> terminal
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

#: States with no outgoing transition (section 7.1: "completed, rejected ->
#: terminal"). ``expired``/``cancelled`` are NOT terminal: the merchant-only
#: verified late-settlement accept may confirm them (section 8.3).
ORDER_TERMINAL_STATES = ("completed", "rejected")

#: Transitions that require an explicit reason recorded in order_events:
#: - confirmed -> cancelled: "cancel after confirm = exceptional, needs reason"
#: - expired|cancelled -> confirmed: merchant-only verified late-settlement
#:   accept (section 8.3) via the oversell/backorder procedure.
REASON_REQUIRED_TRANSITIONS = frozenset(
    {
        ("confirmed", "cancelled"),
        ("expired", "confirmed"),
        ("cancelled", "confirmed"),
    }
)

#: Buyer cancellation is honored only from these states (section 7.1).
BUYER_CANCELLABLE_STATES = ("received", "invoice_pending", "awaiting_payment")


def is_legal_order_transition(from_state: str, to_state: str) -> bool:
    return to_state in ORDER_TRANSITIONS.get(from_state, frozenset())


def order_transition_requires_reason(from_state: str, to_state: str) -> bool:
    return (from_state, to_state) in REASON_REQUIRED_TRANSITIONS


# --- Section 7.2: shipping state machine (literal) ---------------------------

#: not_required -> pending -> processing -> shipped -> delivered;
#: exception is reachable from processing|shipped; recovery from exception to
#: processing|shipped requires an authenticated merchant action and a bounded
#: reason recorded in order_events. Digital orders start and stay not_required.
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


# --- Section 7.3: reservation state machine (literal) -------------------------

#: held -> consumed | released | expired. Only held reservations count in
#: stock_reserved; consumed is applied exactly once inside the settlement
#: transaction (section 8.3).
RESERVATION_STATES = ("held", "consumed", "released", "expired")

RESERVATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "held": frozenset({"consumed", "released", "expired"}),
    "consumed": frozenset(),
    "released": frozenset(),
    "expired": frozenset(),
}


# --- Section 7.4: outbox state machine (literal) -----------------------------

#: pending|partially_published -> claimed -> publishing ->
#: published|pending|partially_published|failed. Zero positive ACKs return
#: the row to pending with backoff; an incomplete nonzero result returns it
#: to partially_published; only exhausted attempts or an explicit permanent
#: policy enter failed. Public rows in pending|claimed|publishing|
#: partially_published|failed may become superseded when a newer
#: aggregate_revision exists; order_msg rows MUST NOT be superseded. A stale
#: claim is reconstructed from durable positive relay_publications and
#: returned to pending or partially_published by a fencing-token CAS.
OUTBOX_STATES = (
    "pending",
    "claimed",
    "publishing",
    "partially_published",
    "published",
    "superseded",
    "failed",
)

OUTBOX_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"claimed", "superseded"}),
    "partially_published": frozenset({"claimed", "superseded"}),
    "claimed": frozenset(
        {"publishing", "pending", "partially_published", "superseded"}
    ),
    "publishing": frozenset(
        {"published", "pending", "partially_published", "failed", "superseded"}
    ),
    "published": frozenset(),
    "superseded": frozenset(),
    "failed": frozenset({"superseded"}),
}

#: Public aggregate rows that a newer revision may supersede (section 7.4).
OUTBOX_SUPERSEDABLE_STATES = (
    "pending",
    "claimed",
    "publishing",
    "partially_published",
    "failed",
)

#: order_msg rows are never superseded (section 7.4).
OUTBOX_NON_SUPERSEDABLE_AGGREGATES = ("order_msg",)


# --- Section 7.5: inbox state machine (literal) -------------------------------

#: received -> validated -> processed; -> rejected (bad signature/shape,
#: terminal); -> quarantined (oversize/malformed/undecryptable, retained for
#: inspection with a bounded reason and no plaintext).
INBOX_STATES = (
    "received",
    "validated",
    "processed",
    "rejected",
    "quarantined",
)

INBOX_TRANSITIONS: dict[str, frozenset[str]] = {
    "received": frozenset({"validated", "rejected", "quarantined"}),
    "validated": frozenset({"processed"}),
    "processed": frozenset(),
    "rejected": frozenset(),
    "quarantined": frozenset(),
}


# --- The single order-state entry path (section 7.1) --------------------------


def insert_order_event_sql(table: str) -> str:
    """Insert one append-only order_events audit row (section 4.7)."""
    return (
        f"INSERT INTO {table}"
        " (id, order_id, from_state, to_state, actor, detail_json, created_at)"
        " VALUES (:id, :order_id, :from_state, :to_state, :actor,"
        " :detail_json, :created_at)"
    )


def _detail_json(reason: str | None, detail: dict | None) -> str | None:
    payload: dict = {}
    if reason is not None:
        payload["reason"] = reason
    if detail:
        payload.update(detail)
    return json.dumps(payload) if payload else None


async def transition_order(
    t: tx_module.DomainTransaction,
    qual_db,
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

    Runs inside the caller's open domain transaction: legality check ->
    compare-and-swap on the expected from-state -> order_events audit row,
    all atomic. Raises ``IllegalTransition`` for a transition outside the
    table (or a missing required reason) and ``TransitionConflict`` when the
    CAS loses (the order moved concurrently). Returns the effective
    from-state.

    ``qual_db`` supplies the schema-qualified table names.
    """
    now = tx_module.db_now() if now is None else now
    orders = qual_db.table("orders")
    events = qual_db.table("order_events")

    if from_state is None:
        rows = await t.fetch_all(
            f"SELECT state FROM {orders} WHERE id = :order_id",
            {"order_id": order_id},
        )
        if not rows:
            raise TransitionConflict(f"order {order_id!r} does not exist")
        from_state = rows[0]["state"]

    if to_state not in ORDER_TRANSITIONS.get(from_state, frozenset()):
        raise IllegalTransition(
            f"illegal order transition {from_state!r} -> {to_state!r}"
            " (section 7.1)"
        )
    if (from_state, to_state) in REASON_REQUIRED_TRANSITIONS and not reason:
        raise IllegalTransition(
            f"transition {from_state!r} -> {to_state!r} requires a reason"
            " (section 7.1)"
        )

    rc = await t.execute(
        tx_module.cas_order_state_sql(orders),
        {
            "to_state": to_state,
            "order_id": order_id,
            "from_state": from_state,
        },
    )
    if rc != 1:
        raise TransitionConflict(
            f"order CAS lost for {order_id!r}"
            f" (expected {from_state!r}, target {to_state!r})"
        )
    await t.execute(
        f"UPDATE {orders} SET updated_at = :now WHERE id = :order_id",
        {"now": now, "order_id": order_id},
    )
    await t.execute(
        insert_order_event_sql(events),
        {
            "id": f"oe_{uuid.uuid4().hex[:16]}",
            "order_id": order_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "detail_json": _detail_json(reason, detail),
            "created_at": now,
        },
    )
    return from_state


async def transition_order_isolated(
    qual_db,
    *,
    order_id: str,
    to_state: str,
    from_state: str | None = None,
    actor: str = "system",
    reason: str | None = None,
    detail: dict | None = None,
    now: int | None = None,
) -> str:
    """``transition_order`` in its own one-statement domain transaction."""
    async with qual_db.connect() as conn:
        async with qual_db.transaction(conn) as t:
            return await transition_order(
                t,
                qual_db,
                order_id=order_id,
                to_state=to_state,
                from_state=from_state,
                actor=actor,
                reason=reason,
                detail=detail,
                now=now,
            )
