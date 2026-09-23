"""02-04 A2/A3 buyer UI contract — the served product/order documents and
public JS must carry the UI-SPEC invariants verbatim: checkout field set,
persistent summary, aria-live validation, layout preset + ≤560px compact
override, verbatim copy, header-only order token, scoped theme emission."""

from __future__ import annotations

import asyncio

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
              "display_name": "buyer shop"},
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
    cid = resp.json()["id"]
    # A physical product (exercises the address field set + shipping
    # options) and a digital one (exercises the minimal field set).
    resp = await client.post(
        f"{API}/shipping",
        json={"title": "post", "service": "standard",
              "base_price_minor": 500, "currency": "SAT",
              "countries": ["US"]},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        f"{API}/products",
        json={
            "catalog_id": cid, "title": "mug", "amount_minor": 4200,
            "currency": "SAT", "visibility": "on-sale",
            "stock_on_hand": 5, "format": "physical",
        },
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    physical = resp.json()
    resp = await client.post(
        f"{API}/products",
        json={
            "catalog_id": cid, "title": "ebook", "amount_minor": 1000,
            "currency": "SAT", "visibility": "on-sale",
            "stock_on_hand": 10, "format": "digital",
        },
        headers=await cookie(),
    )
    digital = resp.json()

    async with DomainTransaction() as tx:
        merchant = await tx.fetch_one(
            "SELECT pubkey FROM merchants WHERE id = :m", {"m": mid},
        )
    pubkey = merchant["pubkey"]
    runtime_env.update({
        "merchant_id": mid, "physical": physical, "digital": digital,
        "pubkey": pubkey,
        "physical_url": f"/gammamarkets/p/{pubkey}/{physical['d_tag']}",
        "digital_url": f"/gammamarkets/p/{pubkey}/{digital['d_tag']}",
    })
    yield


async def test_product_page_checkout_card(runtime_env):
    """A2: the product document embeds the checkout card with the
    invariant field set, persistent summary, and verbatim copy."""
    client = runtime_env["client"]
    resp = await client.get(runtime_env["physical_url"])
    assert resp.status_code == 200
    html = resp.text
    # Checkout card + form contract.
    assert 'id="gm-checkout-card"' in html
    assert 'id="gm-checkout"' in html
    assert 'data-endpoint="/gammamarkets/api/v1/public/checkout"' in html
    assert f'data-merchant="{runtime_env["pubkey"]}"' in html
    assert f'data-d-tag="{runtime_env["physical"]["d_tag"]}"' in html
    assert 'data-layout=' in html
    # Invariant field set — physical address + opt-in email + verbatim
    # consent copy.
    for field in ("country", "line1", "city", "region", "postal_code"):
        assert f'name="{field}"' in html, field
    assert 'name="email_opt_in"' in html
    assert "Send transactional updates. No marketing." in html
    # Persistent Items/Shipping/Total summary.
    assert 'data-sum="items"' in html
    assert 'data-sum="shipping"' in html
    assert 'data-sum="total"' in html
    # aria-live validation channels.
    assert html.count('aria-live="polite"') >= 3
    # Invoice panel + scripts (shared module first).
    assert 'id="gm-invoice-panel"' in html
    assert "public_storefront.js" in html
    assert "public_checkout.js" in html
    # Same-origin vendored QR assets only — no third-party script ever.
    assert "/static/vendor/qrcode.vue.browser.js" in html
    assert "https://" not in html.split("vendor/qrcode")[1].split(">")[0]
    # Protective headers + restrictive CSP (§5.4).
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["referrer-policy"] == "no-referrer"
    csp = resp.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


async def test_digital_product_hides_address_fields(runtime_env):
    client = runtime_env["client"]
    resp = await client.get(runtime_env["digital_url"])
    assert resp.status_code == 200
    html = resp.text
    # Digital format — the address field set is not rendered.
    for field in ("line1", "city", "postal_code", "shipping_option"):
        assert f'name="{field}"' not in html, field
    # Email + consent copy remain (invariant).
    assert 'name="email_opt_in"' in html
    assert "Send transactional updates. No marketing." in html


async def test_order_page_shell(runtime_env):
    """A3: the order-status document carries the status regions, opt-out
    + copy controls, and the fragment-token stripping contract."""
    client = runtime_env["client"]
    resp = await client.get("/gammamarkets/order#tok123")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="gm-order"' in html
    assert 'id="gm-order-state"' in html
    assert 'id="gm-order-checking"' in html
    assert 'id="gm-order-invoice"' in html
    assert 'id="gm-copy-status-link"' in html
    assert 'id="gm-opt-out"' in html
    assert "public_storefront.js" in html
    assert "public_order.js" in html
    assert "Stop order emails" in html
    assert "Copy status link" in html
    assert resp.headers["cache-control"] == "no-store"


async def test_public_js_contracts(runtime_env):
    """The served JS carries the security/UX contracts verbatim."""
    client = runtime_env["client"]

    resp = await client.get(
        "/gammamarkets/static/gammamarkets/js/public_storefront.js"
    )
    assert resp.status_code == 200
    js = resp.text
    # §5.4 token contract — fragment read once, stripped, header-only.
    assert "history.replaceState" in js
    assert "X-Order-Token" in js or "orderToken" in js

    resp = await client.get(
        "/gammamarkets/static/gammamarkets/js/public_checkout.js"
    )
    js = resp.text
    # ≤560px forced compact — responsive safety override.
    assert "(max-width: 560px)" in js
    # Idempotency-Key: ≥128 random bits, reused across retries.
    assert "crypto.getRandomValues" in js
    assert "Idempotency-Key" in js
    # creation_unknown never offers a second invoice.
    assert "creation_unknown" in js
    assert "do not pay a second" in js or "No new invoice" in js
    # Invoice security copy (verbatim).
    assert "Invoice is correlated to this order only" in js
    assert "Waiting for payment" in js

    resp = await client.get(
        "/gammamarkets/static/gammamarkets/js/public_order.js"
    )
    js = resp.text
    # Header-only token + identical invalid-token copy.
    assert "X-Order-Token" in js
    assert "This order link is no longer valid." in js
    assert "On hold — the merchant is reviewing a payment issue." in js


async def test_theme_emission_scoped(runtime_env):
    """Merchant theme tokens emit only inside .gm-public — never admin
    documents and never outside that scope."""
    client = runtime_env["client"]
    # Save a theme through the real PATCH path.
    resp = await client.patch(
        f"{API}/merchants/{runtime_env['merchant_id']}",
        json={"theme": {"preset": "high-contrast"}},
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": client.cookies.get("gm_csrf"),
        },
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(runtime_env["digital_url"])
    assert resp.status_code == 200
    # The emitted block is scoped under .gm-public and carries the
    # high-contrast tokens.
    assert ".gm-public {" in resp.text
    assert "--color-bg: #000000" in resp.text
    # The admin document never receives theme tokens.
    admin = await client.get("/gammamarkets/")
    assert admin.status_code == 200
    assert "--color-bg: #000000" not in admin.text
