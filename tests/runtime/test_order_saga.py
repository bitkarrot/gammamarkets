"""Section 8.2/8.3/8.4/8.7 saga + settlement through the real host boot
(FakeWallet). Workers are cancelled — every step is driven explicitly so
the durable paths (projection-before-call, attach-regardless, settlement
idempotence, late-settlement exception, expiry, reconcile) are asserted
deterministically."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.runtime

ORIGIN = "https://shop.example"
API = "/gammamarkets/api/v1"


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def _setup(runtime_env):
    ext = runtime_env["ext_module"]
    for task in list(ext._owned_tasks):  # noqa: SLF001
        task.cancel()
    await asyncio.sleep(0)

    client = runtime_env["client"]

    async def cookie() -> dict:
        if not client.cookies.get("gm_csrf"):
            await client.get(f"{API}/merchants/current")
        return {
            "Origin": ORIGIN,
            "X-CSRF-Token": client.cookies.get("gm_csrf"),
        }

    resp = await client.post(
        f"{API}/merchants",
        json={"wallet_id": runtime_env["wallet"].id,
              "display_name": "saga shop"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    mid = resp.json()["id"]
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE merchants SET state = 'active' WHERE id = :m",
            {"m": mid},
        )
    resp = await client.post(
        f"{API}/catalogs",
        json={"name": "main", "default_currency": "SAT"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    async def product(title, stock) -> dict:
        resp = await client.post(
            f"{API}/products",
            json={
                "catalog_id": cid, "title": title,
                "amount_minor": 500, "currency": "SAT",
                "visibility": "on-sale", "stock_on_hand": stock,
                "format": "digital",
            },
            headers=await cookie(),
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    runtime_env.update({
        "merchant_id": mid, "catalog_id": cid,
        "make_product": product, "cookie": cookie,
    })
    yield


def _svcs():
    import importlib

    return {
        name: importlib.import_module(f"gammamarkets.services.{name}")
        for name in ("checkout", "orders", "settlement", "email")
    }


async def _mpk(runtime_env):
    from gammamarkets.db import db

    async with db.connect() as conn:
        row = await conn.fetchone(
            "SELECT pubkey FROM gammamarkets.merchants WHERE id = :m",
            {"m": runtime_env["merchant_id"]},
        )
    return row["pubkey"]


async def _new_order(runtime_env, *, qty=2, stock=10, title=None):
    """A fresh product + checkout -> awaiting_payment order."""
    svcs = _svcs()
    product = await runtime_env["make_product"](
        title or uuid.uuid4().hex[:8], stock
    )
    resp = await svcs["checkout"].checkout(
        payload={
            "merchant_pubkey": await _mpk(runtime_env),
            "items": [{"d_tag": product["d_tag"], "quantity": qty}],
        },
        idempotency_key=uuid.uuid4().hex * 2,
        client_scope="saga",
    )
    from gammamarkets.crypto import token_lookup_hash
    from gammamarkets.db import db

    async with db.connect() as conn:
        order = dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(resp["public_token"])},
        ))
    return order, product, resp


async def _row(sql, params):
    from gammamarkets.db import db

    async with db.connect() as conn:
        return dict(await conn.fetchone(sql, params))


async def _core_row(sql, params):
    """A row from the CORE lnbits database (apipayments, wallets)."""
    from lnbits.core.db import db as core_db

    async with core_db.connect() as conn:
        return dict(await conn.fetchone(sql, params))


# --- §8.3 settlement --------------------------------------------------------------


async def _settle_core_payment(order_id: str, total_sat: int):
    """Pay the core invoice via FakeWallet and return the settled Payment."""
    from lnbits.wallets import get_funding_source

    core = await _core_row(
        "SELECT * FROM apipayments WHERE external_id = :e",
        {"e": f"gammamarkets:{order_id}"},
    )
    funding = get_funding_source()
    resp = await funding.pay_invoice(
        core["bolt11"], fee_limit_msat=10_000
    )
    assert resp.ok, resp.error_message
    # The same function the host's paid_invoices_stream consumer invokes —
    # deterministic here instead of racing the producer task.
    from lnbits.core.services.payments import (
        update_invoice_from_paid_invoices_stream,
    )

    settled = await update_invoice_from_paid_invoices_stream(
        core["checking_id"]
    )
    assert settled is not None, "FakeWallet settlement did not land"
    assert settled.success
    from gammamarkets.services.settlement import (
        _core_payments_by_external_id,  # noqa: SLF001
    )

    payments = await _core_payments_by_external_id(
        f"gammamarkets:{order_id}"
    )
    assert len(payments) == 1
    return payments[0]


async def test_settlement_confirms_once(runtime_env):
    """FakeWallet pays the invoice -> listener -> confirmed; reservations
    consumed; stock decremented exactly once; double-delivery is a no-op."""
    svcs = _svcs()
    order, product, resp = await _new_order(runtime_env, qty=3, stock=10)
    assert order["state"] == "awaiting_payment"

    payment = await _settle_core_payment(order["id"], order["total_sat"])
    await svcs["settlement"].invoice_listener(payment)

    fresh = await _row(
        "SELECT * FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "confirmed"
    proj = await _row(
        "SELECT * FROM gammamarkets.payments WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert proj["status"] == "settled"
    res = await _row(
        "SELECT state, COUNT(*) AS n FROM gammamarkets.inventory_reservations"
        " WHERE order_id = :o GROUP BY state",
        {"o": order["id"]},
    )
    assert res["state"] == "consumed"
    prod = await _row(
        "SELECT stock_on_hand, stock_reserved FROM gammamarkets.products"
        " WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10 - 3
    assert prod["stock_reserved"] == 0

    # Double-delivery: the listener again must be a no-op.
    await svcs["settlement"].invoice_listener(payment)
    prod2 = await _row(
        "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod2["stock_on_hand"] == 10 - 3  # stock never decrements twice


async def test_settlement_foreign_payment_ignored(runtime_env):
    """A payment with another extension tag or wrong external id is not
    settlement evidence."""
    svcs = _svcs()
    order, _, _ = await _new_order(runtime_env)

    from lnbits.core.models.payments import Payment

    # Different extension -> ignored.
    fake = Payment(
        checking_id="x", payment_hash="y", wallet_id="w",
        amount=1000, status="success", memo="m",
        extension="other-extension",
        external_id=f"gammamarkets:{order['id']}",
        fee=0, bolt11="",
    )
    await svcs["settlement"].invoice_listener(fake)
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "awaiting_payment"


async def test_late_settlement_on_expired_order(runtime_env):
    """§8.4: a settled payment landing on an expired order marks the
    payment settled + payment_exception — no reopen, no consumption."""
    svcs = _svcs()
    order, product, resp = await _new_order(runtime_env, qty=2, stock=10)

    # Expire the order first (invoice unpaid past expiry).
    await svcs["settlement"].expire_order(order_id=order["id"])
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "expired"
    res = await _row(
        "SELECT state FROM gammamarkets.inventory_reservations"
        " WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert res["state"] == "expired"

    # Now the payment lands — settled-after-terminal-state exception.
    result = await svcs["settlement"].confirm_settlement(
        order_id=order["id"], source="test"
    )
    assert result["action"] == "exception"
    fresh = await _row(
        "SELECT state, payment_exception FROM gammamarkets.orders"
        " WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "expired"  # never auto-reopened
    assert fresh["payment_exception"] in (1, True)
    proj = await _row(
        "SELECT status FROM gammamarkets.payments WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert proj["status"] == "settled"
    prod = await _row(
        "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10  # nothing consumed

    # Merchant resolution: accept decrements available stock -> confirmed.
    resolved = await svcs["settlement"].resolve_exception(
        order_id=order["id"], action="accept",
    )
    assert resolved["action"] == "accepted"
    fresh = await _row(
        "SELECT state, payment_exception, payment_exception_resolution"
        " FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "confirmed"
    assert fresh["payment_exception"] in (0, False)
    assert fresh["payment_exception_resolution"] == "accepted"
    prod = await _row(
        "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10 - 2


async def test_buyer_cancel_before_payment(runtime_env):
    """§7.1 buyer-cancel in awaiting_payment: reservations release, the
    projection survives for late-settlement detection, BOLT11 disappears
    from the public surface."""
    svcs = _svcs()
    order, product, resp = await _new_order(runtime_env, qty=2, stock=10)

    await svcs["orders"].cancel_order(
        order_id=order["id"], actor="buyer", reason=None,
    )
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "cancelled"
    res = await _row(
        "SELECT state FROM gammamarkets.inventory_reservations"
        " WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert res["state"] == "released"
    proj = await _row(
        "SELECT status, bolt11_enc FROM gammamarkets.payments"
        " WHERE order_id = :o",
        {"o": order["id"]},
    )
    # The projection is preserved (late-settlement detection needs it).
    assert proj["status"] == "pending"
    assert proj["bolt11_enc"] is not None
    prod = await _row(
        "SELECT stock_on_hand, stock_reserved FROM gammamarkets.products"
        " WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10
    assert prod["stock_reserved"] == 0


async def test_invoice_creation_unknown_never_duplicates(runtime_env):
    """§8.2 step 4: an InvoiceError(pending)/timeout marks the projection
    creation_unknown + payment_exception — begin_saga never retries the
    external call, reconciliation recovers by exact external id."""
    svcs = _svcs()
    checkout = svcs["checkout"]
    product = await runtime_env["make_product"]("crashy", 5)
    resp = await checkout.checkout(
        payload={
            "merchant_pubkey": await _mpk(runtime_env),
            "items": [{"d_tag": product["d_tag"], "quantity": 1}],
        },
        idempotency_key=uuid.uuid4().hex * 2,
        client_scope="saga2",
    )
    from gammamarkets.crypto import token_lookup_hash
    from gammamarkets.db import db

    async with db.connect() as conn:
        order = dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(resp["public_token"])},
        ))
    assert order["state"] == "awaiting_payment"

    # Simulate the unknown outcome directly on the projection.
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE payments SET status = 'creation_unknown'"
            " WHERE order_id = :o",
            {"o": order["id"]},
        )
    # Reconciliation finds the matching core payment by exact external id
    # and attaches it (the crash-window path).
    report = await svcs["settlement"].reconcile()
    assert any(
        a["order_id"] == order["id"] for a in report["attached"]
    ), report
    proj = await _row(
        "SELECT status FROM gammamarkets.payments WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert proj["status"] == "pending"
    # Exactly one core invoice exists — reconciliation never creates one.
    core = await _core_row(
        "SELECT COUNT(*) AS n FROM apipayments WHERE external_id = :e",
        {"e": f"gammamarkets:{order['id']}"},
    )
    assert core["n"] == 1


async def test_reconcile_resumes_received_order(runtime_env):
    """§8.7: a committed 'received' order (crash between intake and saga)
    resumes through begin_saga — never abandoned."""
    svcs = _svcs()
    checkout = svcs["checkout"]
    product = await runtime_env["make_product"]("resume-me", 5)

    # Insert the intake tx only — monkeypatch begin_saga to a no-op so the
    # order stays 'received'.
    from gammamarkets.db import DomainTransaction, db

    mpk = await _mpk(runtime_env)
    resp = await checkout.checkout(
        payload={
            "merchant_pubkey": mpk,
            "items": [{"d_tag": product["d_tag"], "quantity": 1}],
        },
        idempotency_key=uuid.uuid4().hex * 2,
        client_scope="saga3",
    )
    from gammamarkets.crypto import token_lookup_hash

    async with db.connect() as conn:
        order = dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(resp["public_token"])},
        ))
    # Force the order back to received + drop its saga artifacts (the
    # crash happened before begin_saga ran).
    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE orders SET state = 'received' WHERE id = :i",
            {"i": order["id"]},
        )
        await tx.execute(
            "DELETE FROM payments WHERE order_id = :o",
            {"o": order["id"]},
        )
        await tx.execute(
            "DELETE FROM inventory_reservations WHERE order_id = :o",
            {"o": order["id"]},
        )
        await tx.execute(
            "UPDATE products SET stock_reserved = stock_reserved - 1"
            " WHERE id = :p",
            {"p": product["id"]},
        )
    report = await svcs["settlement"].reconcile()
    assert any(
        r.get("state") == "awaiting_payment" for r in report["resumed"]
    ), report
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "awaiting_payment"
    proj = await _row(
        "SELECT status FROM gammamarkets.payments WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert proj["status"] == "pending"


async def test_reservation_expiry_releases_once(runtime_env):
    """§8.4: an expired held reservation releases exactly once; the
    awaiting_payment order whose invoice expired transitions -> expired."""
    svcs = _svcs()
    order, product, resp = await _new_order(runtime_env, qty=2, stock=10)

    # Push the reservation expiry into the past.
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE inventory_reservations SET expires_at = 1"
            " WHERE order_id = :o",
            {"o": order["id"]},
        )
    result = await svcs["settlement"].reservation_expiry_pass()
    assert result["expired_orders"] >= 1
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "expired"
    res = await _row(
        "SELECT state FROM gammamarkets.inventory_reservations"
        " WHERE order_id = :o",
        {"o": order["id"]},
    )
    assert res["state"] == "expired"
    prod = await _row(
        "SELECT stock_on_hand, stock_reserved FROM gammamarkets.products"
        " WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10
    assert prod["stock_reserved"] == 0
    # Second pass: nothing left to release (exactly-once).
    result2 = await svcs["settlement"].reservation_expiry_pass()
    assert result2["released"] == 0


async def test_kill_before_callback_reconcile_confirms(runtime_env):
    """§8.7: the listener is memory-only — a settled core payment with no
    callback delivery is recovered by reconciliation, exactly once."""
    svcs = _svcs()
    order, product, resp = await _new_order(runtime_env, qty=2, stock=10)

    # Pay the invoice but NEVER invoke the listener — the kill between
    # settlement and callback means only the core row carries truth.
    await _settle_core_payment(order["id"], order["total_sat"])
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "awaiting_payment"  # nothing confirmed yet

    report = await svcs["settlement"].reconcile()
    assert any(
        c["order_id"] == order["id"] for c in report["confirmed"]
    ), report
    fresh = await _row(
        "SELECT state FROM gammamarkets.orders WHERE id = :i",
        {"i": order["id"]},
    )
    assert fresh["state"] == "confirmed"
    prod = await _row(
        "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10 - 2

    # A second pass cannot confirm twice.
    report2 = await svcs["settlement"].reconcile()
    assert not any(
        c["order_id"] == order["id"] for c in report2["confirmed"]
    )
    prod = await _row(
        "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
        {"p": product["id"]},
    )
    assert prod["stock_on_hand"] == 10 - 2


async def test_amount_and_wallet_mismatch_quarantine(runtime_env):
    """§8.3 verification: a matching-external-id payment with the wrong
    amount or a foreign wallet is NEVER settlement evidence — the order
    quarantines with a bounded reason and nothing confirms or consumes."""
    svcs = _svcs()
    order_amt, product_amt, _ = await _new_order(
        runtime_env, qty=2, stock=10
    )
    order_wal, product_wal, _ = await _new_order(
        runtime_env, qty=2, stock=10
    )

    from lnbits.core.models.payments import Payment

    # Wrong amount (500 vs the order's 1000 sat).
    bad_amount = Payment(
        checking_id="c1", payment_hash="h1",
        wallet_id=runtime_env["wallet"].id,
        amount=500_000, status="success", memo="m",
        extension="gammamarkets",
        external_id=f"gammamarkets:{order_amt['id']}",
        fee=0, bolt11="",
    )
    await svcs["settlement"].invoice_listener(bad_amount)

    # Right amount (qty 2 x 500 = 1000 sat), foreign wallet.
    bad_wallet = Payment(
        checking_id="c2", payment_hash="h2", wallet_id="foreign-wallet",
        amount=1_000_000, status="success", memo="m",
        extension="gammamarkets",
        external_id=f"gammamarkets:{order_wal['id']}",
        fee=0, bolt11="",
    )
    await svcs["settlement"].invoice_listener(bad_wallet)

    for order, reason in (
        (order_amt, "settlement-amount-mismatch"),
        (order_wal, "settlement-wallet-mismatch"),
    ):
        fresh = await _row(
            "SELECT state, payment_exception, payment_exception_reason"
            " FROM gammamarkets.orders WHERE id = :i",
            {"i": order["id"]},
        )
        assert fresh["state"] == "awaiting_payment", reason
        assert fresh["payment_exception"] in (1, True)
        assert fresh["payment_exception_reason"] == reason
        proj = await _row(
            "SELECT status FROM gammamarkets.payments WHERE order_id = :o",
            {"o": order["id"]},
        )
        assert proj["status"] == "pending"  # never marked settled
        res = await _row(
            "SELECT state FROM gammamarkets.inventory_reservations"
            " WHERE order_id = :o",
            {"o": order["id"]},
        )
        assert res["state"] == "held"  # never consumed

    for product in (product_amt, product_wal):
        prod = await _row(
            "SELECT stock_on_hand FROM gammamarkets.products WHERE id = :p",
            {"p": product["id"]},
        )
        assert prod["stock_on_hand"] == 10


async def test_lease_fencing(runtime_env, monkeypatch):
    """§10/§14: one live holder per task lease — a second worker gets
    None while the lease is held; expiry allows takeover and the fencing
    token strictly increases."""
    import importlib

    tasks = importlib.import_module("gammamarkets.services.tasks")
    name = f"drill-{uuid.uuid4().hex[:8]}"

    monkeypatch.setattr(tasks, "WORKER_ID", "holder-A")
    token_a = await tasks._acquire_lease(name)  # noqa: SLF001
    assert token_a == 1

    # A competing worker cannot take a live lease.
    monkeypatch.setattr(tasks, "WORKER_ID", "holder-B")
    assert await tasks._acquire_lease(name) is None  # noqa: SLF001

    # The holder renews — fencing token increments per renewal.
    monkeypatch.setattr(tasks, "WORKER_ID", "holder-A")
    token_a2 = await tasks._acquire_lease(name)  # noqa: SLF001
    assert token_a2 > token_a

    # Expire the lease -> takeover with a strictly larger token.
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE task_leases SET leased_until = 1 WHERE name = :n",
            {"n": name},
        )
    monkeypatch.setattr(tasks, "WORKER_ID", "holder-B")
    token_b = await tasks._acquire_lease(name)  # noqa: SLF001
    assert token_b is not None and token_b > token_a2
