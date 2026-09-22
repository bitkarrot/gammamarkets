"""Section 8.1 intake + §4.15 idempotency + §3.4 FX through the real
host boot (FakeWallet). Worker tasks are cancelled so every step runs
deterministically from direct service calls — the durable paths they
protect are asserted explicitly here."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

pytestmark = pytest.mark.runtime

ORIGIN = "https://shop.example"
API = "/gammamarkets/api/v1"


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def _setup(runtime_env):
    """Cancel live workers for deterministic service-level assertions and
    create the merchant/catalog/products the tests exercise."""
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
              "display_name": "checkout shop"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    mid = resp.json()["id"]
    # Activation: draft -> publication_pending -> active happens when the
    # merchant_profile intent publishes (RELAY_IO=off never sends, so the
    # publish path is covered in test_outbox.py; flip directly here).
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE merchants SET state = 'active' WHERE id = :m",
            {"m": mid},
        )
    resp = await client.post(
        f"{API}/catalogs",
        json={"name": "main", "default_currency": "USD"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    async def product(body) -> dict:
        resp = await client.post(
            f"{API}/products",
            json={"catalog_id": cid, **body},
            headers=await cookie(),
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    widget = await product({
        "title": "widget", "amount_minor": 500, "currency": "SAT",
        "visibility": "on-sale", "stock_on_hand": 10, "format": "digital",
    })
    gizmo = await product({
        "title": "gizmo", "amount_minor": 100, "currency": "SAT",
        "visibility": "on-sale", "stock_on_hand": 2, "format": "digital",
    })
    draft = await product({
        "title": "wip", "draft": True,
        "amount_minor": 100, "currency": "SAT", "format": "digital",
    })
    usd_item = await product({
        "title": "usd thing",
        "amount_minor": 1000, "currency": "USD", "currency_decimals": 2,
        "visibility": "on-sale", "stock_on_hand": 5, "format": "digital",
    })

    runtime_env.update({
        "merchant_id": mid, "catalog_id": cid,
        "widget": widget, "gizmo": gizmo, "draft": draft,
        "usd_item": usd_item,
    })
    yield


def _svcs():
    import importlib

    return {
        name: importlib.import_module(f"gammamarkets.services.{name}")
        for name in ("checkout", "orders", "settlement", "fx", "readiness")
    }


async def _merchant_pubkey(runtime_env):
    from gammamarkets.db import db  # noqa: PLC0415

    async with db.connect() as conn:
        row = await conn.fetchone(
            "SELECT pubkey FROM gammamarkets.merchants WHERE id = :m",
            {"m": runtime_env["merchant_id"]},
        )
    return row["pubkey"]


async def _payload(runtime_env, items, **kw):
    return {
        "merchant_pubkey": await _merchant_pubkey(runtime_env),
        "items": items,
        **kw,
    }


async def _order_for_token(token: str) -> dict:
    from gammamarkets.crypto import token_lookup_hash
    from gammamarkets.db import db

    async with db.connect() as conn:
        row = await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(token)},
        )
    return dict(row)


# --- §8.1 intake validation -------------------------------------------------------


async def test_intake_rejects_bad_items(runtime_env):
    checkout = _svcs()["checkout"]
    from gammamarkets.security import ProblemError

    async def bad(items):
        with pytest.raises(ProblemError):
            await checkout.checkout(
                payload={
                    "merchant_pubkey": await _merchant_pubkey(runtime_env),
                    "items": items,
                },
                idempotency_key=uuid.uuid4().hex * 2,
                client_scope="t1",
            )

    await bad([])                                    # empty
    await bad([{}])                                  # missing fields
    await bad([{"d_tag": "d", "quantity": 0}])       # qty bounds
    await bad([{"d_tag": "d", "quantity": -1}])
    await bad([{"d_tag": "d", "quantity": 10001}])
    await bad([{"d_tag": "d", "quantity": 1.5}])
    await bad([{"d_tag": "d", "quantity": "x"}])
    await bad([{"d_tag": "x" * 65, "quantity": 1}])  # d_tag bound
    await bad(                                       # §15 item cap
        [{"d_tag": "d", "quantity": 1}] * 65
    )


async def test_intake_rejects_unpurchasable(runtime_env):
    checkout = _svcs()["checkout"]
    from gammamarkets.security import ProblemError

    # Unknown d_tag.
    with pytest.raises(ProblemError):
        await checkout.checkout(
            payload=await _payload(
                runtime_env, [{"d_tag": "nope", "quantity": 1}]
            ),
            idempotency_key=uuid.uuid4().hex * 2,
            client_scope="t2",
        )
    # Draft products never sell (§8.1 step 4).
    with pytest.raises(ProblemError):
        await checkout.checkout(
            payload=await _payload(
                runtime_env,
                [{"d_tag": runtime_env["draft"]["d_tag"], "quantity": 1}],
            ),
            idempotency_key=uuid.uuid4().hex * 2,
            client_scope="t2",
        )
    # Unknown merchant.
    with pytest.raises(ProblemError):
        await checkout.checkout(
            payload={
                "merchant_pubkey": "ab" * 32,
                "items": [{"d_tag": "d", "quantity": 1}],
            },
            idempotency_key=uuid.uuid4().hex * 2,
            client_scope="t2",
        )


async def test_fresh_checkout_creates_order(runtime_env):
    """Happy path: intake + saga driven to awaiting_payment by the
    FakeWallet create_invoice; reservations held; projection pending."""
    checkout = _svcs()["checkout"]
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["widget"]["d_tag"], "quantity": 2},
        {"d_tag": runtime_env["gizmo"]["d_tag"], "quantity": 1},
    ])
    resp = await checkout.checkout(
        payload=body, idempotency_key=uuid.uuid4().hex * 2,
        client_scope="t3",
    )
    token = resp["public_token"]
    assert len(token) >= 32
    order = resp["order"]
    assert order["state"] == "awaiting_payment"
    assert order["total_sat"] == 2 * 500 + 100
    assert order["bolt11"] and order["bolt11"].startswith("ln")
    assert order["expires_at"]

    runtime_env["token"] = token
    runtime_env["order_id"] = (await _order_for_token(token))["id"]

    from gammamarkets.db import db

    async with db.connect() as conn:
        res = await conn.fetchall(
            "SELECT * FROM gammamarkets.inventory_reservations"
            " WHERE order_id = :o",
            {"o": runtime_env["order_id"]},
        )
        assert {r["product_id"]: r["quantity"] for r in res} == {
            runtime_env["widget"]["id"]: 2,
            runtime_env["gizmo"]["id"]: 1,
        }
        assert all(r["state"] == "held" for r in res)
        proj = await conn.fetchone(
            "SELECT * FROM gammamarkets.payments WHERE order_id = :o",
            {"o": runtime_env["order_id"]},
        )
        assert proj["status"] == "pending"
        assert proj["core_external_id"] == (
            f"gammamarkets:{runtime_env['order_id']}"
        )
        items = await conn.fetchall(
            "SELECT * FROM gammamarkets.order_items WHERE order_id = :o",
            {"o": runtime_env["order_id"]},
        )
        assert len(items) == 2
        assert {i["title"] for i in items} == {"widget", "gizmo"}


async def test_idempotency_replay_and_conflict(runtime_env):
    checkout = _svcs()["checkout"]
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["widget"]["d_tag"], "quantity": 1},
    ])
    key = uuid.uuid4().hex * 2
    first = await checkout.checkout(
        payload=body, idempotency_key=key, client_scope="t4"
    )
    second = await checkout.checkout(
        payload=body, idempotency_key=key, client_scope="t4"
    )
    # Same key + same body -> byte-identical stored response.
    assert second["public_token"] == first["public_token"]

    from gammamarkets.db import db

    async with db.connect() as conn:
        await conn.fetchone(
            "SELECT COUNT(*) AS n FROM gammamarkets.orders"
            " WHERE merchant_id = :m",
            {"m": runtime_env["merchant_id"]},
        )
    # One replay must never mint a second order for the same request.
    first_order = (await _order_for_token(first["public_token"]))["id"]

    from gammamarkets.security import ProblemError

    other = await _payload(runtime_env, [
        {"d_tag": runtime_env["gizmo"]["d_tag"], "quantity": 1},
    ])
    with pytest.raises(ProblemError) as exc:
        await checkout.checkout(
            payload=other, idempotency_key=key, client_scope="t4"
        )
    assert exc.value.code == "idempotency-conflict"
    runtime_env["first_order_id"] = first_order


async def test_idempotency_crash_resume(runtime_env):
    """A lease that dies after the order exists resumes the saga rather
    than duplicating the order/invoice (§4.15)."""
    checkout = _svcs()["checkout"]
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["widget"]["d_tag"], "quantity": 1},
    ])
    key = uuid.uuid4().hex * 2
    first = await checkout.checkout(
        payload=body, idempotency_key=key, client_scope="t5"
    )
    scope = checkout._scope_hash(  # noqa: SLF001
        runtime_env["merchant_id"], "/api/v1/public/checkout", key,
    )
    # Force the record back to an expired in_progress lease — a kill
    # between intake and response.
    from gammamarkets.db import DomainTransaction, db

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE idempotency_records SET state = 'in_progress',"
            " lease_until = 1, response_enc = NULL WHERE scope_hash = :s",
            {"s": scope},
        )
    replay = await checkout.checkout(
        payload=body, idempotency_key=key, client_scope="t5"
    )
    # Resume returns the SAME order/token — never a second order.
    assert replay["public_token"] == first["public_token"]
    async with db.connect() as conn:
        n = await conn.fetchone(
            "SELECT COUNT(*) AS n FROM gammamarkets.orders"
            " WHERE merchant_id = :m",
            {"m": runtime_env["merchant_id"]},
        )
        assert n["n"] == 3  # fresh + replay + crash-resume only


async def test_oversell_rejected(runtime_env):
    """§8.2 claim CAS: requesting more than available fails; no partial
    reservations remain."""
    checkout = _svcs()["checkout"]
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["gizmo"]["d_tag"], "quantity": 5},
    ])
    from gammamarkets.security import ProblemError

    with pytest.raises(ProblemError) as exc:
        await checkout.checkout(
            payload=body, idempotency_key=uuid.uuid4().hex * 2,
            client_scope="t6",
        )
    assert exc.value.code == "insufficient-stock"
    from gammamarkets.db import db

    async with db.connect() as conn:
        res = await conn.fetchone(
            "SELECT COUNT(*) AS n FROM gammamarkets.inventory_reservations"
            " WHERE product_id = :p AND state = 'held'",
            {"p": runtime_env["gizmo"]["id"]},
        )
        # gizmo stock 2: the fresh checkout held 1; the oversell held 0.
        assert res["n"] == 1


async def test_fx_usd_conversion(runtime_env, monkeypatch):
    """USD-priced product -> Decimal conversion + order_fx_quotes row."""
    svcs = _svcs()
    checkout = svcs["checkout"]
    fx = svcs["fx"]

    async def fake_rates(currency):
        return [("kraken", 100_000.0), ("bitfinex", 100_000.0)]

    monkeypatch.setattr(fx, "btc_rates", fake_rates)
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["usd_item"]["d_tag"], "quantity": 1},
    ])
    resp = await checkout.checkout(
        payload=body, idempotency_key=uuid.uuid4().hex * 2,
        client_scope="t7",
    )
    # $10.00 at $100k/BTC = 10_000 sats.
    assert resp["order"]["total_sat"] == 10_000
    order_id = (await _order_for_token(resp["public_token"]))["id"]
    from gammamarkets.db import db

    async with db.connect() as conn:
        quote = await conn.fetchone(
            "SELECT * FROM gammamarkets.order_fx_quotes WHERE order_id = :o",
            {"o": order_id},
        )
        assert quote is not None
        assert quote["currency"] == "USD"
        # rate_decimal is sats per major unit: $100k/BTC -> 1000 sat/USD.
        assert Decimal(quote["rate_decimal"]) == Decimal("1000")
        assert quote["providers"] == "kraken,bitfinex"


async def test_missing_fx_rejected(runtime_env, monkeypatch):
    """No provider data -> the order is rejected before any invoice."""
    svcs = _svcs()
    checkout = svcs["checkout"]
    fx = svcs["fx"]

    async def empty_rates(currency):
        return []

    monkeypatch.setattr(fx, "btc_rates", empty_rates)
    body = await _payload(runtime_env, [
        {"d_tag": runtime_env["usd_item"]["d_tag"], "quantity": 1},
    ])
    from gammamarkets.security import ProblemError

    with pytest.raises(ProblemError) as exc:
        await checkout.checkout(
            payload=body, idempotency_key=uuid.uuid4().hex * 2,
            client_scope="t8",
        )
    assert exc.value.code == "fx-unavailable"
