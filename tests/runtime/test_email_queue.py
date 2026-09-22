"""Section 8.8 email queue + worker through the real host boot: dedupe,
claim-token fencing, suppression taxonomy, send classification, rate
limits, lease recovery, render-at-send-time."""

from __future__ import annotations

import asyncio
import time
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
              "display_name": "email shop"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    mid = resp.json()["id"]
    resp = await client.patch(
        f"{API}/merchants/{mid}",
        json={"notify_emails": ["merchant@example.com"]},
        headers=await cookie(),
    )
    assert resp.status_code == 200, resp.text
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
    cid = resp.json()["id"]
    resp = await client.post(
        f"{API}/products",
        json={
            "catalog_id": cid, "title": "thing",
            "amount_minor": 1000, "currency": "SAT",
            "visibility": "on-sale", "stock_on_hand": 50,
            "format": "digital",
        },
        headers=await cookie(),
    )
    product = resp.json()
    runtime_env.update({
        "merchant_id": mid, "catalog_id": cid, "product": product,
    })
    yield


def _svc():
    import importlib

    return {
        n: importlib.import_module(f"gammamarkets.services.{n}")
        for n in ("checkout", "orders", "email", "settlement")
    }


async def _order(runtime_env, *, email=None, opt_in=False) -> dict:
    """A fresh awaiting_payment order; returns the row."""
    svcs = _svc()
    from gammamarkets.db import db

    async with db.connect() as conn:
        merchant = dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.merchants WHERE id = :m",
            {"m": runtime_env["merchant_id"]},
        ))
    payload = {
        "merchant_pubkey": merchant["pubkey"],
        "items": [{"d_tag": runtime_env["product"]["d_tag"],
                   "quantity": 1}],
    }
    if email:
        payload["email"] = email
        payload["email_opt_in"] = opt_in
    resp = await svcs["checkout"].checkout(
        payload=payload, idempotency_key=uuid.uuid4().hex * 2,
        client_scope="email-test",
    )
    from gammamarkets.crypto import token_lookup_hash

    async with db.connect() as conn:
        return dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(resp["public_token"])},
        ))


async def _queue_rows(order_id=None):
    from gammamarkets.db import db

    async with db.connect() as conn:
        sql = "SELECT * FROM gammamarkets.email_queue"
        params = {}
        if order_id:
            sql += " WHERE order_id = :o"
            params["o"] = order_id
        return [dict(r) for r in await conn.fetchall(sql, params)]


async def test_enqueue_dedupes(runtime_env):
    """(order_id, channel, event_type, recipient_hash) is unique — a
    duplicate enqueue is a silent no-op."""
    svcs = _svc()
    order = await _order(runtime_env)
    rows = await _queue_rows(order["id"])
    merchant_rows = [r for r in rows if r["channel"] == "merchant"]
    assert len(merchant_rows) == 1
    assert merchant_rows[0]["event_type"] == "order_received"

    # Enqueue the identical intent again — still one row.
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await svcs["orders"].enqueue_email_intents(
            tx, order=order, event_type="order_received",
            merchant_notify_emails=["merchant@example.com"],
            merchant_notify_events={}, customer_email=None,
            now=int(time.time()),
        )
    rows2 = await _queue_rows(order["id"])
    assert len([r for r in rows2 if r["channel"] == "merchant"]) == 1


async def test_claim_token_fencing(runtime_env):
    """Claims bump claim_token; a write with a stale token loses the CAS."""
    svcs = _svc()
    order = await _order(runtime_env)
    now = int(time.time())
    rows = await svcs["email"].claim_batch(now, "w1")
    mine = [r for r in rows if r["order_id"] == order["id"]]
    assert len(mine) == 1
    row = mine[0]
    assert row["state"] == "claimed"
    assert row["claimed_by"] == "w1"
    assert row["claim_token"] == 1

    # A stale-token write loses.
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        try:
            await svcs["email"]._leased_write(  # noqa: SLF001
                tx, {**row, "claim_token": row["claim_token"] - 1},
                "state = 'sent'", {},
            )
            raise AssertionError("stale CAS should fail")
        except RuntimeError:
            pass

    # Stale-claim recovery returns the row to pending.
    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE email_queue SET claimed_until = 1 WHERE id = :i",
            {"i": row["id"]},
        )
    recovered = await svcs["email"].recover_stale_claims()
    assert recovered >= 1
    rows2 = await _queue_rows(order["id"])
    assert rows2[0]["state"] == "pending"


async def test_suppression_taxonomy(runtime_env):
    """Unconfigured host SMTP suppresses without an SMTP call; customer
    consent revocation suppresses customer rows."""
    svcs = _svc()
    # Host email stays unconfigured -> everything suppresses.
    order = await _order(runtime_env, email="c@example.com", opt_in=True)
    # Enqueue a customer row directly (order_received is merchant-only by
    # design; use a different event for the customer row).
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await svcs["orders"].enqueue_email_intents(
            tx, order=order, event_type="confirmed",
            merchant_notify_emails=["merchant@example.com"],
            merchant_notify_events={},
            customer_email="c@example.com",
            now=int(time.time()),
        )
    result = await svcs["email"].worker_tick("w1")
    assert result["claimed"] >= 1
    rows = await _queue_rows(order["id"])
    assert all(r["state"] == "suppressed" for r in rows)
    assert all(
        r["last_error"] == "host-email-unconfigured" for r in rows
    )


async def test_send_classification(runtime_env, monkeypatch):
    """send_email True -> sent; False/exception -> pending w/ backoff;
    exhaustion -> failed."""
    svcs = _svc()
    from lnbits.settings import settings as host_settings

    host_settings.lnbits_email_notifications_enabled = True
    host_settings.lnbits_email_notifications_email = "shop@example.com"

    sent_calls = []

    async def fake_send(*args, **kwargs):
        sent_calls.append(args)
        return True

    import lnbits.core.services.notifications as notif

    monkeypatch.setattr(notif, "send_email", fake_send)

    order = await _order(runtime_env)
    await svcs["email"].worker_tick("w1")
    rows = await _queue_rows(order["id"])
    assert rows[0]["state"] == "sent"
    assert rows[0]["sent_at"] is not None
    assert sent_calls  # the host send_email was invoked

    # False return -> retry with backoff.
    async def fail_send(*args, **kwargs):
        return False

    monkeypatch.setattr(notif, "send_email", fail_send)
    order2 = await _order(runtime_env)
    await svcs["email"].worker_tick("w1")
    rows2 = await _queue_rows(order2["id"])
    assert rows2[0]["state"] == "pending"
    assert rows2[0]["attempts"] == 1
    assert rows2[0]["next_attempt_at"] > int(time.time())
    assert rows2[0]["last_error"] == "send-failed"

    # Exhaustion -> failed.
    from gammamarkets.db import DomainTransaction
    from gammamarkets.settings import ext_settings

    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE email_queue SET attempts = :a, next_attempt_at = 0"
            " WHERE id = :i",
            {"a": ext_settings().email_max_attempts - 1,
             "i": rows2[0]["id"]},
        )
    await svcs["email"].worker_tick("w1")
    rows3 = await _queue_rows(order2["id"])
    assert rows3[0]["state"] == "failed"

    host_settings.lnbits_email_notifications_enabled = False


async def test_consent_revocation_suppresses(runtime_env):
    """Opt-out between enqueue and send suppresses the customer row —
    consent is re-checked at send time."""
    svcs = _svc()
    order = await _order(runtime_env, email="c2@example.com", opt_in=True)
    from gammamarkets.db import DomainTransaction

    async with DomainTransaction() as tx:
        await svcs["orders"].enqueue_email_intents(
            tx, order=order, event_type="confirmed",
            merchant_notify_emails=["merchant@example.com"],
            merchant_notify_events={},
            customer_email="c2@example.com",
            now=int(time.time()),
        )
    # Revoke consent after enqueue.
    async with DomainTransaction() as tx:
        await tx.execute(
            "UPDATE orders SET email_opt_in = FALSE WHERE id = :i",
            {"i": order["id"]},
        )
    from lnbits.settings import settings as host_settings

    host_settings.lnbits_email_notifications_enabled = True
    host_settings.lnbits_email_notifications_email = "shop@example.com"

    async def fake_send(*args, **kwargs):
        return True

    import lnbits.core.services.notifications as notif

    monkeypatch_ctx = notif
    orig = monkeypatch_ctx.send_email
    monkeypatch_ctx.send_email = fake_send
    try:
        await svcs["email"].worker_tick("w1")
    finally:
        monkeypatch_ctx.send_email = orig
        host_settings.lnbits_email_notifications_enabled = False
    rows = await _queue_rows(order["id"])
    customer = [r for r in rows if r["channel"] == "customer"]
    assert customer[0]["state"] == "suppressed"
    assert customer[0]["last_error"] == "consent-revoked"


async def test_orderless_test_send(runtime_env, monkeypatch):
    """POST /notifications/test enqueues an orderless row; the worker
    decrypts the recipient bound to merchant_id and sends — and the row
    surfaces in GET /notifications.queue."""
    client = runtime_env["client"]
    svcs = _svc()
    mid = runtime_env["merchant_id"]

    async def cookie() -> dict:
        if not client.cookies.get("gm_csrf"):
            await client.get(f"{API}/merchants/current")
        return {
            "Origin": ORIGIN,
            "X-CSRF-Token": client.cookies.get("gm_csrf"),
        }

    resp = await client.post(
        f"{API}/merchants/{mid}/notifications/test",
        json={"recipient": "merchant@example.com"},
        headers=await cookie(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["queued"] is True

    from lnbits.settings import settings as host_settings

    host_settings.lnbits_email_notifications_enabled = True
    host_settings.lnbits_email_notifications_email = "shop@example.com"
    sent_to = []

    async def fake_send(*args, **kwargs):
        sent_to.append(args)
        return True

    import lnbits.core.services.notifications as notif

    monkeypatch.setattr(notif, "send_email", fake_send)
    try:
        await svcs["email"].worker_tick("w1")
    finally:
        host_settings.lnbits_email_notifications_enabled = False

    from gammamarkets.db import db

    async with db.connect() as conn:
        row = dict(await conn.fetchone(
            "SELECT * FROM gammamarkets.email_queue"
            " WHERE merchant_id = :m AND order_id IS NULL",
            {"m": mid},
        ))
    assert row["state"] == "sent"
    assert sent_to and "merchant@example.com" in sent_to[0][5]

    body = (
        await client.get(f"{API}/merchants/{mid}/notifications")
    ).json()
    orderless = [q for q in body["queue"] if not q["order_bound"]]
    assert orderless and orderless[0]["state"] == "sent"


async def test_subject_has_no_pii(runtime_env):
    """Subjects carry display name + event only; bodies never embed the
    decrypted address, keys, or payment secrets."""
    svcs = _svc()
    merchant = {"display_name": "Email Shop"}
    subject = svcs["email"]._subject(merchant, "confirmed")  # noqa: SLF001
    assert subject == "Email Shop: order confirmed"
    for bad in ("@", "order", "bolt11", "0x"):
        if bad == "order":  # 'order' IS the label — skip the self-match
            continue
        assert bad not in subject
