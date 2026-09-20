"""Executable model of the reservation/invoice saga: sections 8.2, 8.3, 8.4,
and 8.7 against the Task-1 schema, plus the controllable fake LNbits payment
boundary whose real behaviors were qualified in P0-03.

What the fake models (and nothing more — the qualified P0-03 outcome set):

- ``create_invoice`` outcomes programmable per test: success (a unique core
  payment with payment_hash/bolt11/expiry/wallet snapshots), definitive
  rejection, and timeout/unknown;
- a core payment store queryable by EXACT ``core_external_id`` that can
  simulate the crash window (LNbits persisted an invoice before the extension
  persisted its local projection) — the store is populated even when the
  outcome is "unknown", via ``unknown_persisted``;
- a settlement trigger that can be fired late or while the order is
  cancelled, with programmable callback delivery (settle the core payment
  while suppressing the invoice-paid callback, so the section 17
  kill-between-settlement-and-callback drill and reconciliation-driven
  recovery are both expressible);
- a pause gate (an asyncio event) so tests can cancel concurrently with
  in-flight invoice creation;
- per-order ``create_invoice`` call counts (the no-second-invoice evidence).

The saga steps (each is separately callable so tests can kill at every
boundary):

1. ``begin`` -> ``_step1_claim``: the section 8.2 step-1 transaction (Task 1)
   including the ``creating`` payment projection with the deterministic
   ``core_external_id = "gammamarkets:<order.id>"``;
2. invoice creation through the fake;
3. ``attach``: the second transaction — persisting hash/checking id/BOLT11/
   expiry and wallet snapshots to the local projection REGARDLESS of whether
   the order is ``invoice_pending`` or ``cancelled``; entering
   ``awaiting_payment`` and aligning reservation expiries only in the first
   case; never delivering BOLT11 or enqueuing a payment request for a
   cancelled order (the projection is retained for late-settlement
   detection);
4. ``cancel`` (received|invoice_pending|awaiting_payment) releasing held
   reservations exactly once; ``_mark_rejection`` (definitive rejection:
   projection failed, release/reject only an invoice_pending order);
   ``_mark_unknown`` (timeout/unknown: status=creation_unknown +
   payment_exception=true, never a second invoice);
5. ``reconcile``: section 8.2 step 5 (creating|creation_unknown projections
   queried by exact external id, independent of orders.state) plus the
   remaining section 8.7 bullets (pending-payment status routing, received
   order resume, type-2 re-enqueue);
6. ``confirm_settlement``: the section 8.3 settlement-confirm transaction —
   one transaction, idempotent by construction, reached identically from a
   delivered invoice-paid callback and from reconciliation (which is what
   makes callback loss recoverable). A settlement on an expired or
   pre-payment-cancelled order marks the payment settled, sets
   ``payment_exception``, changes no state, and consumes no reservations
   (section 8.4: a late payment never auto-reopens the order).

Synthetic BOLT11 strings are non-secret stand-ins stored in the ``*_enc``
columns; the section 11.3 envelope discipline for real secrets is qualified
by the P0-09 surface (harness/email.py).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from harness import state as state_module
from harness import tx


class LNbitsRejection(Exception):
    """LNbits definitively rejected invoice creation (qualified outcome)."""


class LNbitsTimeout(Exception):
    """Invoice creation timed out / returned unknown (qualified outcome)."""


class CriticalMultiMatch(Exception):
    """More than one core payment with one external id: critical manual
    exception; nothing is delivered automatically (section 8.2 step 5)."""


@dataclass
class CorePayment:
    """A payment as LNbits core holds it (the extension's authority)."""

    core_external_id: str
    payment_hash: str
    checking_id: str
    bolt11: str
    expiry_at: int
    amount_sat: int
    wallet_id: str
    source_wallet_id: str
    status: str = "pending"  # pending | settled | expired
    settled_at: int | None = None
    order_id: str = ""


@dataclass
class FakeLNbitsCore:
    """Controllable fake of the LNbits payment boundary (see module docs)."""

    create_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    outcomes: dict[str, str] = field(default_factory=dict)
    unknown_persisted: set[str] = field(default_factory=set)
    core: dict[str, list[CorePayment]] = field(default_factory=dict)
    deliver_callbacks: bool = True
    callbacks: list[dict] = field(default_factory=list)
    _callback_handler: Callable[[dict], Awaitable[None]] | None = None
    pause_enabled: bool = False
    pause_gate: asyncio.Event = field(default_factory=asyncio.Event)
    in_flight: asyncio.Event = field(default_factory=asyncio.Event)
    _seq: int = 0

    def on_invoice_paid(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Register the invoice-paid callback (task_manager listener stand-in)."""
        self._callback_handler = handler

    def _persist(
        self,
        *,
        order_id: str,
        core_external_id: str,
        amount_sat: int,
        wallet_id: str,
        source_wallet_id: str,
        expiry_at: int,
    ) -> CorePayment:
        self._seq += 1
        payment = CorePayment(
            order_id=order_id,
            core_external_id=core_external_id,
            payment_hash=f"hash-{self._seq:08d}-{order_id}",
            checking_id=f"checking-{self._seq:08d}",
            bolt11=f"lnbc{amount_sat}1fake-{self._seq:08d}-{order_id}",
            expiry_at=expiry_at,
            amount_sat=amount_sat,
            wallet_id=wallet_id,
            source_wallet_id=source_wallet_id,
        )
        # LNbits persists the invoice BEFORE returning it — the crash window
        # (core payment exists; the extension's local projection may not).
        self.core.setdefault(core_external_id, []).append(payment)
        return payment

    async def create_invoice(
        self,
        *,
        order_id: str,
        core_external_id: str,
        amount_sat: int,
        wallet_id: str,
        source_wallet_id: str,
        expiry_at: int,
    ) -> CorePayment:
        """Create an invoice through the fake core.

        The pause gate fires before anything is persisted, so a test can
        cancel the order while invoice creation is genuinely in flight.
        """
        self.create_calls[order_id] += 1
        if self.pause_enabled:
            self.in_flight.set()
            await self.pause_gate.wait()
            self.in_flight.clear()
        outcome = self.outcomes.get(order_id, "success")
        if outcome == "rejected":
            raise LNbitsRejection(
                f"LNbits definitively rejected invoice for {order_id}"
            )
        if outcome == "unknown":
            if order_id in self.unknown_persisted:
                # LNbits persisted the invoice BEFORE the timeout hit: the
                # core store has it, but the extension only ever observed
                # the timeout — recovery goes through the external-id query,
                # never through the returned invoice object.
                self._persist(
                    order_id=order_id,
                    core_external_id=core_external_id,
                    amount_sat=amount_sat,
                    wallet_id=wallet_id,
                    source_wallet_id=source_wallet_id,
                    expiry_at=expiry_at,
                )
            raise LNbitsTimeout(f"invoice creation for {order_id} timed out")
        return self._persist(
            order_id=order_id,
            core_external_id=core_external_id,
            amount_sat=amount_sat,
            wallet_id=wallet_id,
            source_wallet_id=source_wallet_id,
            expiry_at=expiry_at,
        )

    async def settle(
        self, core_external_id: str, *, deliver_callback: bool | None = None
    ) -> bool:
        """Settle the core payment(s) for an external id.

        Callback delivery is programmable: suppress it to express the
        section 17 kill-between-settlement-and-callback drill. Returns
        whether the invoice-paid callback was delivered.
        """
        payments = self.core.get(core_external_id, [])
        for payment in payments:
            payment.status = "settled"
        deliver = self.deliver_callbacks if deliver_callback is None else deliver_callback
        if deliver and self._callback_handler is not None:
            for payment in payments:
                record = {
                    "extension": "gammamarkets",
                    "external_id": core_external_id,
                    "payment_hash": payment.payment_hash,
                    "checking_id": payment.checking_id,
                    "amount_sat": payment.amount_sat,
                }
                self.callbacks.append(record)
                await self._callback_handler(record)
        return deliver and self._callback_handler is not None

    def expire(self, core_external_id: str) -> None:
        for payment in self.core.get(core_external_id, []):
            payment.status = "expired"

    def add_extra_core_payment(self, core_external_id: str, **kwargs) -> CorePayment:
        """Inject an additional core payment with the SAME external id.

        The multi-match critical-exception path (section 8.2 step 5: more
        than one match is a manual exception, nothing delivered).
        """
        self._seq += 1
        payment = CorePayment(
            core_external_id=core_external_id,
            payment_hash=kwargs.get("payment_hash", f"hash-{self._seq:08d}-extra"),
            checking_id=kwargs.get("checking_id", f"checking-{self._seq:08d}-extra"),
            bolt11=kwargs.get("bolt11", f"lnbc1fake-{self._seq:08d}-extra"),
            expiry_at=kwargs.get("expiry_at", 0),
            amount_sat=kwargs.get("amount_sat", 0),
            wallet_id=kwargs.get("wallet_id", "wallet"),
            source_wallet_id=kwargs.get("source_wallet_id", "wallet"),
            order_id=kwargs.get("order_id", ""),
        )
        self.core.setdefault(core_external_id, []).append(payment)
        return payment

    def query_by_external_id(self, core_external_id: str) -> list[CorePayment]:
        """Exact external-id query (the section 8.2 recovery key)."""
        return list(self.core.get(core_external_id, []))

    def payment_status(self, core_external_id: str) -> str | None:
        statuses = {p.status for p in self.core.get(core_external_id, [])}
        if len(statuses) == 1:
            return statuses.pop()
        return "ambiguous" if statuses else None


def core_external_id_for(order_id: str) -> str:
    """The deterministic recovery key: ``gammamarkets:<order.id>`` (section 4.8)."""
    return f"gammamarkets:{order_id}"


class InvoiceSaga:
    """The executable section 8.2/8.3/8.4/8.7 saga model."""

    def __init__(
        self,
        qual_db,
        fake: FakeLNbitsCore,
        *,
        wallet_id: str = "wallet-main",
        source_wallet_id: str = "wallet-main",
        reservation_ttl_s: int = 900,
    ) -> None:
        self.qual_db = qual_db
        self.fake = fake
        self.wallet_id = wallet_id
        self.source_wallet_id = source_wallet_id
        self.reservation_ttl_s = reservation_ttl_s
        #: Evidence of BOLT11 deliveries + payment-request enqueues: only an
        #: order that actually entered awaiting_payment ever appears here.
        self.deliveries: list[dict] = []

    # --- helpers -----------------------------------------------------------

    async def _items(self, order_id: str) -> list[dict]:
        rows = await self.qual_db.fetch_all(
            f"SELECT product_id, quantity FROM {self.qual_db.table('order_items')}"
            " WHERE order_id = :order_id ORDER BY product_id",
            {"order_id": order_id},
        )
        return [
            {
                "product_id": row["product_id"],
                "qty": row["quantity"],
                "reservation_id": f"res-{order_id}-{row['product_id']}",
            }
            for row in rows
        ]

    async def _order(self, t, order_id: str) -> dict:
        rows = await t.fetch_all(
            f"SELECT * FROM {self.qual_db.table('orders')} WHERE id = :id",
            {"id": order_id},
        )
        if not rows:
            raise KeyError(f"order {order_id!r} does not exist")
        return rows[0]

    async def _payment(self, t, order_id: str) -> dict:
        rows = await t.fetch_all(
            f"SELECT * FROM {self.qual_db.table('payments')} WHERE order_id = :id",
            {"id": order_id},
        )
        if not rows:
            raise KeyError(f"payment projection for {order_id!r} does not exist")
        return rows[0]

    async def _enqueue_intent(
        self,
        t,
        *,
        intent_id: str,
        merchant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_revision: int,
        event_kind: int,
        payload: dict | None = None,
        now: int,
    ) -> bool:
        """Idempotent outbox intent insert (deterministic id).

        ``ON CONFLICT DO NOTHING`` keeps the insert atomic and idempotent
        without poisoning the surrounding transaction (PostgreSQL aborts a
        transaction after any constraint violation, so an IntegrityError
        catch-and-continue would break the dialect).
        """
        rc = await t.execute(
            f"INSERT INTO {self.qual_db.table('outbox_events')}"
            " (id, merchant_id, aggregate_type, aggregate_id,"
            "  aggregate_revision, event_kind, state, next_attempt_at,"
            "  created_at, updated_at)"
            " VALUES (:id, :merchant_id, :aggregate_type, :aggregate_id,"
            "  :aggregate_revision, :event_kind, 'pending', 0, :now, :now)"
            " ON CONFLICT DO NOTHING",
            {
                "id": intent_id,
                "merchant_id": merchant_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "aggregate_revision": aggregate_revision,
                "event_kind": event_kind,
                "now": now,
            },
        )
        if rc == 0:
            return False  # already enqueued — idempotent no-op
        if payload is not None:
            import json

            await t.execute(
                f"UPDATE {self.qual_db.table('outbox_events')} SET payload_json = :p"
                " WHERE id = :id",
                {"p": json.dumps(payload), "id": intent_id},
            )
        return True

    async def _release_reservations(
        self, t, *, order_id: str, to_state: str, now: int
    ) -> int:
        """Release held reservations exactly once, decrementing stock_reserved.

        Only rows still in state ``held`` flip; the stock decrement is bound
        to that flip inside the same transaction, so a second release pass
        finds no held rows and is a no-op. Returns the total quantity
        released.
        """
        released = 0
        held = await t.fetch_all(
            f"SELECT id, product_id, quantity FROM"
            f" {self.qual_db.table('inventory_reservations')}"
            " WHERE order_id = :order_id AND state = 'held'",
            {"order_id": order_id},
        )
        for row in held:
            rc = await t.execute(
                f"UPDATE {self.qual_db.table('inventory_reservations')}"
                " SET state = :to_state, updated_at = :now"
                " WHERE id = :id AND state = 'held'",
                {"to_state": to_state, "now": now, "id": row["id"]},
            )
            if rc != 1:  # pragma: no cover - held rows cannot vanish mid-tx
                raise tx.SagaConflict(f"reservation CAS lost for {row['id']}")
            await t.execute(
                f"UPDATE {self.qual_db.table('products')}"
                " SET stock_reserved = stock_reserved - :qty, updated_at = :now"
                " WHERE id = :product_id",
                {"qty": row["quantity"], "now": now, "product_id": row["product_id"]},
            )
            released += row["quantity"]
        return released

    # --- step 1-4: begin ---------------------------------------------------

    async def begin(
        self, *, order_id: str, items: list[dict] | None = None, now: int | None = None
    ) -> dict:
        """Section 8.2 steps 1-4 end to end.

        Raises ``SagaConflict`` when the step-1 claim/CAS loses (e.g. the
        order was cancelled first, or another worker already began).
        """
        now = tx.db_now() if now is None else now
        items = items if items is not None else await self._items(order_id)
        order = await self._order_standalone(order_id)
        payment = {
            "id": f"pay-{order_id}",
            "core_external_id": core_external_id_for(order_id),
            "checking_id_enc": None,
            "wallet_refs_enc": None,
            "wallet_id_hash": f"wh-{self.wallet_id}",
            "source_wallet_id_hash": f"wh-{self.source_wallet_id}",
            "amount_sat": order["total_sat"],
        }
        # Step 1: conditional claim + CAS + reservations + creating projection.
        await tx.claim_and_reserve_multi(
            self.qual_db,
            items=items,
            order_id=order_id,
            expires_at=now + self.reservation_ttl_s,
            now=now,
            payment=payment,
        )
        # Step 2: invoice creation through the fake (extension/external-id
        # correlation is the deterministic core_external_id).
        try:
            invoice = await self.fake.create_invoice(
                order_id=order_id,
                core_external_id=payment["core_external_id"],
                amount_sat=order["total_sat"],
                wallet_id=self.wallet_id,
                source_wallet_id=self.source_wallet_id,
                expiry_at=now + self.reservation_ttl_s,
            )
        except LNbitsRejection:
            await self._mark_rejection(order_id, now=now)
            return {"order_id": order_id, "outcome": "rejected"}
        except LNbitsTimeout:
            await self._mark_unknown(order_id, now=now)
            return {"order_id": order_id, "outcome": "creation_unknown"}
        # Step 3: the second attach transaction.
        return await self.attach(order_id=order_id, invoice=invoice, now=now)

    async def _order_standalone(self, order_id: str) -> dict:
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('orders')} WHERE id = :id",
            {"id": order_id},
        )
        if not rows:
            raise KeyError(f"order {order_id!r} does not exist")
        return rows[0]

    async def attach(
        self, *, order_id: str, invoice: CorePayment, now: int | None = None
    ) -> dict:
        """Section 8.2 step 3: the second (attach) transaction.

        Persists hash/checking id/BOLT11/expiry and wallet snapshots to the
        local projection regardless of whether the order is invoice_pending
        or cancelled. Entering awaiting_payment, aligning reservation
        expiries, and delivering the payment request happen ONLY for an
        invoice_pending order; a cancelled order keeps its state, receives
        no delivery, and retains the projection for late-settlement
        detection.
        """
        now = tx.db_now() if now is None else now
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                order = await self._order(t, order_id)
                rc = await t.execute(
                    f"UPDATE {self.qual_db.table('payments')}"
                    " SET payment_hash = :payment_hash, checking_id_enc = :checking_id,"
                    " bolt11_enc = :bolt11, wallet_refs_enc = :wallet_refs,"
                    " status = 'pending'"
                    " WHERE order_id = :order_id AND core_external_id = :core_external_id",
                    {
                        "payment_hash": invoice.payment_hash,
                        "checking_id": invoice.checking_id.encode(),
                        "bolt11": invoice.bolt11.encode(),
                        "wallet_refs": f"{invoice.wallet_id}|{invoice.source_wallet_id}".encode(),
                        "order_id": order_id,
                        "core_external_id": invoice.core_external_id,
                    },
                )
                if rc != 1:
                    raise tx.SagaConflict(
                        f"attach failed: no creating projection for {order_id!r}"
                        f" with external id {invoice.core_external_id!r}"
                    )
                if order["state"] == "invoice_pending":
                    # The decoded BOLT11 expiry is authoritative for
                    # still-held reservations (section 8.2).
                    await t.execute(
                        f"UPDATE {self.qual_db.table('inventory_reservations')}"
                        " SET expires_at = :expiry_at, updated_at = :now"
                        " WHERE order_id = :order_id AND state = 'held'",
                        {
                            "expiry_at": invoice.expiry_at,
                            "now": now,
                            "order_id": order_id,
                        },
                    )
                    await state_module.transition_order(
                        t,
                        self.qual_db,
                        order_id=order_id,
                        from_state="invoice_pending",
                        to_state="awaiting_payment",
                        actor="system",
                        detail={"payment_hash": invoice.payment_hash},
                        now=now,
                    )
                    # Deliver the payment request exactly once (the type-2
                    # outbox row; deterministic id keeps re-enqueue idempotent).
                    await self._enqueue_intent(
                        t,
                        intent_id=f"obx-{order_id}-payment-request",
                        merchant_id=order["merchant_id"],
                        aggregate_type="order_msg",
                        aggregate_id=order_id,
                        aggregate_revision=1,
                        event_kind=2,
                        payload={
                            "order_id": order_id,
                            "payment_hash": invoice.payment_hash,
                        },
                        now=now,
                    )
                    self.deliveries.append(
                        {
                            "order_id": order_id,
                            "payment_hash": invoice.payment_hash,
                            "bolt11": invoice.bolt11,
                        }
                    )
                    return {
                        "order_id": order_id,
                        "outcome": "attached",
                        "delivered": True,
                    }
                # Cancelled (or any other state): keep the projection for
                # late-settlement detection; NO delivery, NO payment request.
                return {
                    "order_id": order_id,
                    "outcome": "attached-cancelled"
                    if order["state"] == "cancelled"
                    else f"attached-{order['state']}",
                    "delivered": False,
                }

    # --- step 4: cancellation / rejection / unknown --------------------------

    async def cancel(
        self,
        *,
        order_id: str,
        actor: str = "buyer",
        reason: str | None = None,
        now: int | None = None,
    ) -> dict:
        """Section 7.1/8.2 step 4: cancellation releases held stock exactly once.

        Honored only from received|invoice_pending|awaiting_payment. A second
        cancellation of an already-cancelled order is a no-op that releases
        nothing (exactly-once release).
        """
        now = tx.db_now() if now is None else now
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                order = await self._order(t, order_id)
                if order["state"] == "cancelled":
                    return {"order_id": order_id, "action": "no-op-already-cancelled"}
                if order["state"] not in state_module.BUYER_CANCELLABLE_STATES:
                    raise state_module.IllegalTransition(
                        f"cancellation from {order['state']!r} is not honored"
                        " (section 7.1)"
                    )
                await state_module.transition_order(
                    t,
                    self.qual_db,
                    order_id=order_id,
                    from_state=order["state"],
                    to_state="cancelled",
                    actor=actor,
                    reason=reason,
                    now=now,
                )
                released = await self._release_reservations(
                    t, order_id=order_id, to_state="released", now=now
                )
                # Type-3 cancelled status intent (Gamma projection, section 7.1).
                await self._enqueue_intent(
                    t,
                    intent_id=f"obx-{order_id}-status-cancelled",
                    merchant_id=order["merchant_id"],
                    aggregate_type="order_msg",
                    aggregate_id=order_id,
                    aggregate_revision=1,
                    event_kind=3,
                    payload={"order_id": order_id, "status": "cancelled"},
                    now=now,
                )
                return {"order_id": order_id, "action": "cancelled", "released": released}

    async def _mark_rejection(self, order_id: str, *, now: int) -> None:
        """Definitive rejection: projection failed; release/reject ONLY an
        invoice_pending order; a cancelled order stays cancelled."""
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                await t.execute(
                    f"UPDATE {self.qual_db.table('payments')} SET status = 'failed'"
                    " WHERE order_id = :order_id"
                    " AND status IN ('creating', 'creation_unknown')",
                    {"order_id": order_id},
                )
                order = await self._order(t, order_id)
                if order["state"] == "invoice_pending":
                    await state_module.transition_order(
                        t,
                        self.qual_db,
                        order_id=order_id,
                        from_state="invoice_pending",
                        to_state="rejected",
                        actor="system",
                        reason="invoice-creation-rejected",
                        now=now,
                    )
                    await self._release_reservations(
                        t, order_id=order_id, to_state="released", now=now
                    )

    async def _mark_unknown(self, order_id: str, *, now: int) -> None:
        """Timeout/unknown: status=creation_unknown + payment_exception=true.

        The state remains invoice_pending with the orthogonal exception flag
        (section 7.1); a second invoice is NEVER created — recovery goes
        through reconciliation by exact external id.
        """
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                await t.execute(
                    f"UPDATE {self.qual_db.table('payments')} SET status = 'creation_unknown'"
                    " WHERE order_id = :order_id AND status = 'creating'",
                    {"order_id": order_id},
                )
                await t.execute(
                    f"UPDATE {self.qual_db.table('orders')}"
                    " SET payment_exception = TRUE,"
                    " payment_exception_reason = 'invoice-creation-unknown',"
                    " updated_at = :now WHERE id = :order_id",
                    {"now": now, "order_id": order_id},
                )

    # --- section 8.3: settlement confirm ------------------------------------

    async def confirm_settlement(
        self, *, order_id: str, now: int | None = None, source: str = "callback"
    ) -> dict:
        """The section 8.3 settlement-confirm transaction.

        One transaction, idempotent by construction: a payment already
        marked settled is a no-op. Confirm path (awaiting_payment): mark the
        local payment settled, consume each held reservation (stock_on_hand
        and stock_reserved each -= qty exactly once), transition the order
        to confirmed with its order_events row, and enqueue the type-3
        confirmed + stock/state-republication intents. Terminal branch
        (expired / pre-payment cancelled): mark settled, set
        payment_exception=true, change no state, consume no reservations.
        """
        now = tx.db_now() if now is None else now
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                order = await self._order(t, order_id)
                rc = await t.execute(
                    f"UPDATE {self.qual_db.table('payments')}"
                    " SET status = 'settled', settled_at = :now"
                    " WHERE order_id = :order_id"
                    " AND status IN ('pending', 'creating', 'creation_unknown')",
                    {"now": now, "order_id": order_id},
                )
                if rc != 1:
                    payment = await self._payment(t, order_id)
                    if payment["status"] == "settled":
                        # Section 8.3 step 1: already settled -> no-op.
                        return {
                            "order_id": order_id,
                            "action": "no-op",
                            "reason": "already-settled",
                            "source": source,
                        }
                    raise tx.SagaConflict(
                        f"settlement confirm CAS lost for payment of {order_id!r}"
                    )

                if order["state"] != "awaiting_payment":
                    # Section 8.3 terminal branch (expired or pre-payment
                    # cancelled, or any unexpected state): mark settled +
                    # payment_exception, no state change, no consumption.
                    await t.execute(
                        f"UPDATE {self.qual_db.table('orders')}"
                        " SET payment_exception = TRUE,"
                        " payment_exception_reason = 'settled-after-terminal-state',"
                        " updated_at = :now WHERE id = :order_id",
                        {"now": now, "order_id": order_id},
                    )
                    return {
                        "order_id": order_id,
                        "action": "exception",
                        "order_state": order["state"],
                        "source": source,
                    }

                # Consume held reservations exactly once.
                held = await t.fetch_all(
                    f"SELECT id, product_id, quantity FROM"
                    f" {self.qual_db.table('inventory_reservations')}"
                    " WHERE order_id = :order_id AND state = 'held'",
                    {"order_id": order_id},
                )
                for row in held:
                    rc = await t.execute(
                        f"UPDATE {self.qual_db.table('inventory_reservations')}"
                        " SET state = 'consumed', updated_at = :now"
                        " WHERE id = :id AND state = 'held'",
                        {"now": now, "id": row["id"]},
                    )
                    if rc != 1:  # pragma: no cover
                        raise tx.SagaConflict(
                            f"reservation consume CAS lost for {row['id']}"
                        )
                    await t.execute(
                        f"UPDATE {self.qual_db.table('products')}"
                        " SET stock_on_hand = stock_on_hand - :qty,"
                        " stock_reserved = stock_reserved - :qty,"
                        " revision = revision + 1, updated_at = :now"
                        " WHERE id = :product_id",
                        {
                            "qty": row["quantity"],
                            "now": now,
                            "product_id": row["product_id"],
                        },
                    )
                await state_module.transition_order(
                    t,
                    self.qual_db,
                    order_id=order_id,
                    from_state="awaiting_payment",
                    to_state="confirmed",
                    actor="system",
                    detail={"source": source},
                    now=now,
                )
                # Outbox intents: type-3 confirmed message + stock/state
                # republication for each affected product (new revision).
                await self._enqueue_intent(
                    t,
                    intent_id=f"obx-{order_id}-status-confirmed",
                    merchant_id=order["merchant_id"],
                    aggregate_type="order_msg",
                    aggregate_id=order_id,
                    aggregate_revision=1,
                    event_kind=3,
                    payload={"order_id": order_id, "status": "confirmed"},
                    now=now,
                )
                for row in held:
                    product = await t.fetch_all(
                        f"SELECT revision FROM {self.qual_db.table('products')}"
                        " WHERE id = :product_id",
                        {"product_id": row["product_id"]},
                    )
                    await self._enqueue_intent(
                        t,
                        intent_id=f"obx-{order_id}-stock-{row['product_id']}",
                        merchant_id=order["merchant_id"],
                        aggregate_type="product",
                        aggregate_id=row["product_id"],
                        aggregate_revision=product[0]["revision"],
                        event_kind=30402,
                        payload={"order_id": order_id, "reason": "stock-republication"},
                        now=now,
                    )
                return {
                    "order_id": order_id,
                    "action": "confirmed",
                    "consumed": len(held),
                    "source": source,
                }

    # --- section 8.4: expiry --------------------------------------------------

    async def expire_order(
        self, *, order_id: str, now: int | None = None
    ) -> dict:
        """Invoice expired unpaid: release reservations (expired state),
        transition awaiting_payment -> expired, publish type-3 cancelled."""
        now = tx.db_now() if now is None else now
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                order = await self._order(t, order_id)
                if order["state"] != "awaiting_payment":
                    raise state_module.IllegalTransition(
                        f"expiry applies to awaiting_payment orders, not"
                        f" {order['state']!r}"
                    )
                await state_module.transition_order(
                    t,
                    self.qual_db,
                    order_id=order_id,
                    from_state="awaiting_payment",
                    to_state="expired",
                    actor="system",
                    reason="invoice-expired-unpaid",
                    now=now,
                )
                released = await self._release_reservations(
                    t, order_id=order_id, to_state="expired", now=now
                )
                await self._enqueue_intent(
                    t,
                    intent_id=f"obx-{order_id}-status-cancelled",
                    merchant_id=order["merchant_id"],
                    aggregate_type="order_msg",
                    aggregate_id=order_id,
                    aggregate_revision=1,
                    event_kind=3,
                    payload={"order_id": order_id, "status": "cancelled"},
                    now=now,
                )
                return {"order_id": order_id, "action": "expired", "released": released}

    # --- section 8.2 step 5 + section 8.7: reconciliation ----------------------

    async def reconcile(
        self,
        *,
        now: int | None = None,
        uncertainty_window_s: int = 300,
    ) -> dict:
        """One reconciliation pass (section 8.2 step 5 + section 8.7).

        Outbox stale-claim requeue and inbox reprocessing live in
        harness/queues.py (the queue models own their recovery).
        """
        now = tx.db_now() if now is None else now
        report: dict[str, list] = {
            "resumed": [],
            "attached": [],
            "failed_projections": [],
            "confirmed": [],
            "expired": [],
            "critical": [],
            "reenqueued_payment_requests": [],
        }

        # Section 8.7 bullet 3: resume committed received orders by
        # idempotently beginning section 8.2 — never abandon an order merely
        # because a crash occurred between intake and reservation.
        received = await self.qual_db.fetch_all(
            f"SELECT id FROM {self.qual_db.table('orders')} WHERE state = 'received'"
        )
        for row in received:
            order_id = row["id"]
            try:
                result = await self.begin(order_id=order_id, now=now)
                report["resumed"].append({"order_id": order_id, **result})
            except tx.SagaConflict:
                report["resumed"].append(
                    {"order_id": order_id, "action": "already-begun"}
                )

        # Section 8.2 step 5: projections in creating|creation_unknown,
        # queried by exact core_external_id, independent of orders.state.
        projections = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('payments')}"
            " WHERE status IN ('creating', 'creation_unknown')"
        )
        for payment in projections:
            matches = self.fake.query_by_external_id(payment["core_external_id"])
            if len(matches) > 1:
                # Critical manual exception: nothing delivered automatically.
                async with self.qual_db.connect() as conn:
                    async with self.qual_db.transaction(conn) as t:
                        await t.execute(
                            f"UPDATE {self.qual_db.table('orders')}"
                            " SET payment_exception = TRUE,"
                            " payment_exception_reason = 'multiple-core-payments',"
                            " updated_at = :now WHERE id = :order_id",
                            {"now": now, "order_id": payment["order_id"]},
                        )
                report["critical"].append(
                    {
                        "order_id": payment["order_id"],
                        "core_external_id": payment["core_external_id"],
                        "matches": len(matches),
                    }
                )
                continue
            if len(matches) == 1:
                result = await self.attach(
                    order_id=payment["order_id"], invoice=matches[0], now=now
                )
                report["attached"].append(result)
                continue
            # Zero matches: only after the five-minute uncertainty window may
            # the projection be marked failed (and only an invoice_pending
            # order released/rejected; cancelled remains cancelled).
            if now - payment["created_at"] >= uncertainty_window_s:
                await self._mark_rejection(payment["order_id"], now=now)
                report["failed_projections"].append(
                    {"order_id": payment["order_id"], "reason": "zero-matches-after-window"}
                )

        # Section 8.7 bullet 1: for each payments.status=pending, query the
        # core payment status; settled -> section 8.3; expired -> expiry path.
        pending = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('payments')} WHERE status = 'pending'"
        )
        for payment in pending:
            core_status = self.fake.payment_status(payment["core_external_id"])
            if core_status == "settled":
                result = await self.confirm_settlement(
                    order_id=payment["order_id"], now=now, source="reconciliation"
                )
                report["confirmed"].append(result)
            elif core_status == "expired":
                result = await self.expire_order(
                    order_id=payment["order_id"], now=now
                )
                report["expired"].append(result)

        # Section 8.7 last bullet: an awaiting_payment order with a local
        # payment but no type-2 outbox row gets it enqueued idempotently.
        awaiting = await self.qual_db.fetch_all(
            f"SELECT o.id AS order_id, o.merchant_id FROM"
            f" {self.qual_db.table('orders')} o"
            f" JOIN {self.qual_db.table('payments')} p ON p.order_id = o.id"
            " WHERE o.state = 'awaiting_payment' AND p.status = 'pending'"
        )
        for row in awaiting:
            order_id = row["order_id"]
            existing = await self.qual_db.fetch_all(
                f"SELECT id FROM {self.qual_db.table('outbox_events')}"
                " WHERE id = :id",
                {"id": f"obx-{order_id}-payment-request"},
            )
            if not existing:
                async with self.qual_db.connect() as conn:
                    async with self.qual_db.transaction(conn) as t:
                        enqueued = await self._enqueue_intent(
                            t,
                            intent_id=f"obx-{order_id}-payment-request",
                            merchant_id=row["merchant_id"],
                            aggregate_type="order_msg",
                            aggregate_id=order_id,
                            aggregate_revision=1,
                            event_kind=2,
                            payload={"order_id": order_id},
                            now=now,
                        )
                        if enqueued:
                            report["reenqueued_payment_requests"].append(order_id)
        return report
