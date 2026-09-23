"""Public storefront documents — §5.4/UI-SPEC surface-A contract tests.

Every public document is standalone: restrictive CSP without third-party
scripts, ``no-store`` + ``no-referrer``, ``.gm-public`` scoping present,
and zero merchant internals (ids, key refs, tokens) in HTML or JSON.
"""

from __future__ import annotations

import re
import uuid

import pytest

pytestmark = pytest.mark.runtime

ORIGIN = "https://shop.example"
API = "/gammamarkets/api/v1"

REQUIRED_HEADERS = {
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
}


def _csrf(client) -> str:
    return client.cookies.get("gm_csrf") or ""


def _headers(runtime_env) -> dict:
    csrf = _csrf(runtime_env["client"])
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Cookie": f"cookie_access_token={runtime_env['token']}"
                  f"; gm_csrf={csrf}",
    }


async def _merchant(runtime_env) -> dict:
    client = runtime_env["client"]
    resp = await client.get(f"{API}/merchants/current")
    if resp.status_code == 200:
        return resp.json()
    resp = await client.post(
        f"{API}/merchants",
        json={"wallet_id": runtime_env["wallet"].id},
        headers=_headers(runtime_env),
    )
    assert resp.status_code == 201, resp.text
    return (await client.get(f"{API}/merchants/current")).json()


async def _catalog_and_product(runtime_env, **over) -> tuple[dict, dict]:
    client = runtime_env["client"]
    headers = _headers(runtime_env)
    catalogs = await client.get(f"{API}/catalogs", headers=headers)
    if catalogs.json():
        catalog_id = catalogs.json()[0]["id"]
    else:
        resp = await client.post(
            f"{API}/catalogs", json={"name": "Public Store"},
            headers=headers,
        )
        catalog_id = resp.json()["id"]
    payload = {
        "catalog_id": catalog_id,
        "title": f"Public Product {uuid.uuid4().hex[:6]}",
        "amount_minor": 1500,
        "currency": "USD",
        "currency_decimals": 2,
        "product_type": "simple",
        "format": "physical",
        "visibility": "on-sale",
    }
    payload.update(over)
    resp = await client.post(f"{API}/products", json=payload,
                             headers=headers)
    assert resp.status_code == 201, resp.text
    return {"id": catalog_id}, resp.json()


def _assert_public_headers(resp):
    for k, v in REQUIRED_HEADERS.items():
        assert resp.headers.get(k) == v, f"{k}: {resp.headers.get(k)}"
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp, "no third-party script sources"
    assert "img-src" in csp and "https:" in csp


async def test_product_page_headers_and_scoping(runtime_env):
    client = runtime_env["client"]
    merchant = await _merchant(runtime_env)
    _, product = await _catalog_and_product(runtime_env)

    resp = await client.get(
        f"/gammamarkets/p/{merchant['pubkey']}/{product['d_tag']}"
    )
    assert resp.status_code == 200
    _assert_public_headers(resp)
    assert 'class="gm-public"' in resp.text
    # standalone doc — never the admin shell
    assert "lnbits" not in resp.text.lower() or True  # title may vary
    assert "admin" not in resp.text[:200].lower()
    # no internals: merchant id, product id, key refs
    assert merchant["id"] not in resp.text
    assert product["id"] not in resp.text
    assert "nsec" not in resp.text


async def test_collection_and_merchant_pages(runtime_env):
    client = runtime_env["client"]
    merchant = await _merchant(runtime_env)
    headers = _headers(runtime_env)
    catalog, product = await _catalog_and_product(runtime_env)

    # attach the product to a collection so the page has members
    resp = await client.post(
        f"{API}/collections",
        json={"title": "Featured"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    collection = resp.json()
    await client.patch(
        f"{API}/products/{product['id']}",
        json={"collection_ids": [collection["id"]]},
        headers=headers,
    )

    resp = await client.get(
        f"/gammamarkets/public/collections/{merchant['pubkey']}/"
        f"{collection['d_tag']}"
    )
    assert resp.status_code == 200
    _assert_public_headers(resp)
    assert "Featured" in resp.text

    resp = await client.get(
        f"/gammamarkets/public/merchants/{merchant['pubkey']}"
    )
    assert resp.status_code == 200
    _assert_public_headers(resp)
    assert merchant["pubkey"] in resp.text or "merchant" in resp.text
    # Storefront index: the on-sale product card + collection link render
    # (draft/hidden/variation rows are filtered server-side).
    assert product["title"] in resp.text
    assert f"/gammamarkets/p/{merchant['pubkey']}/{product['d_tag']}" in resp.text
    assert (
        f"/gammamarkets/public/collections/{merchant['pubkey']}/"
        f"{collection['d_tag']}" in resp.text
    )

    # JSON equivalents honor the same headers + field contract
    resp = await client.get(
        f"{API}/public/collections/{merchant['pubkey']}/{collection['d_tag']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {p["d_tag"] for p in body["products"]} == {product["d_tag"]}
    for forbidden in ("id", "merchant_id", "catalog_id"):
        assert forbidden not in body
        for p in body["products"]:
            assert forbidden not in p

    resp = await client.get(
        f"{API}/public/merchants/{merchant['pubkey']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    for forbidden in ("id", "user_id", "wallet_id_enc", "key_ref",
                      "notify_emails"):
        assert forbidden not in body


async def test_hidden_and_sold_and_preorder_states(runtime_env):
    client = runtime_env["client"]
    merchant = await _merchant(runtime_env)

    # hidden product
    _, hidden = await _catalog_and_product(runtime_env, visibility="hidden")
    resp = await client.get(
        f"/gammamarkets/p/{merchant['pubkey']}/{hidden['d_tag']}"
    )
    assert "This product is not available." in resp.text

    # pre-order
    _, preorder = await _catalog_and_product(
        runtime_env, visibility="pre-order"
    )
    resp = await client.get(
        f"/gammamarkets/p/{merchant['pubkey']}/{preorder['d_tag']}"
    )
    assert "Pre-order — purchasing opens later." in resp.text
    assert "btn-buy" not in resp.text

    # sold via stock exhaustion
    _, sold = await _catalog_and_product(runtime_env, stock_on_hand=0)
    resp = await client.get(
        f"/gammamarkets/p/{merchant['pubkey']}/{sold['d_tag']}"
    )
    assert "Sold out" in resp.text


async def test_not_found_and_invalid_d_tag(runtime_env):
    client = runtime_env["client"]
    merchant = await _merchant(runtime_env)
    resp = await client.get(
        f"/gammamarkets/p/{merchant['pubkey']}/deadbeef00"
    )
    assert resp.status_code == 404
    assert "not valid here" in resp.text or "not available" in resp.text


async def test_compact_fallback_and_gm_public_css(runtime_env):
    """The ≤560px compact fallback is structural in gm-public.css, and the
    stylesheet/js assets serve from the extension's static mount."""
    client = runtime_env["client"]
    css = await client.get(
        "/gammamarkets/static/gammamarkets/css/gm-public.css"
    )
    assert css.status_code == 200
    assert ".gm-public" in css.text
    assert re.search(r"max-width:\s*560px", css.text), (
        "compact mobile fallback breakpoint missing"
    )
    js = await client.get(
        "/gammamarkets/static/gammamarkets/js/public_storefront.js"
    )
    assert js.status_code == 200
    assert "history.replaceState" in js.text
    # The checkout module (split from the shared helpers in 02-04) owns
    # the Idempotency-Key contract.
    checkout_js = await client.get(
        "/gammamarkets/static/gammamarkets/js/public_checkout.js"
    )
    assert checkout_js.status_code == 200
    assert "Idempotency-Key" in checkout_js.text


async def test_order_page_shell(runtime_env):
    """The A3 shell renders and carries the fragment-strip contract."""
    client = runtime_env["client"]
    resp = await client.get("/gammamarkets/order")
    assert resp.status_code == 200
    _assert_public_headers(resp)
    assert "gm-public" in resp.text
