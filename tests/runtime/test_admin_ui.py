"""02-04 admin shell + surfaces contract — the served admin document and
its JS modules carry the UI-SPEC invariants: one nav section, Linear
Split workspace grid, verbatim copy, no-secret boundaries, legal-action
surface, and host-palette-only theming (no merchant tokens)."""

from __future__ import annotations

import asyncio
import re

import pytest
import pytest_asyncio

pytestmark = pytest.mark.runtime

ORIGIN = "https://shop.example"
API = "/gammamarkets/api/v1"
JS = "/gammamarkets/static/gammamarkets/js"


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
              "display_name": "admin shop"},
        headers=await cookie(),
    )
    assert resp.status_code == 201, resp.text
    runtime_env["merchant_id"] = resp.json()["id"]
    yield


async def test_admin_shell_document(runtime_env):
    """The admin page mounts inside the host shell with all modules."""
    resp = await runtime_env["client"].get("/gammamarkets/")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="gm-admin-root"' in html
    # One nav section — exactly the four surfaces.
    for nav in ("orders", "catalog", "publications", "settings"):
        assert f'data-gm-nav="{nav}"' in html, nav
    # Every module script loads.
    for mod in ("admin_app", "admin_orders", "admin_catalog",
                "admin_publications", "admin_settings",
                "admin_notifications"):
        assert f"{mod}.js" in html, mod


async def test_admin_verbatim_copy(runtime_env):
    """UI-SPEC copy strings render verbatim in the document."""
    resp = await runtime_env["client"].get("/gammamarkets/")
    html = resp.text
    # B1 search placeholder.
    assert "Search order or buyer" in html
    # B2 relay outcomes are delivery evidence — never settlement.
    assert "delivery evidence" in html.lower()
    # B1 mobile navigation.
    assert "← Back to orders" in html
    # B6 boundary + layout notes and the B4 key-import note are JS
    # constants bound through Vue — assert them in the module.
    settings_js = (await runtime_env["client"].get(
        f"{JS}/admin_settings.js")).text
    assert (
        "Appearance applies to your public storefront only. It never"
        " changes the admin area, checkout fields, totals, validation,"
        " or payment states." in settings_js
    )
    assert "Mobile always uses the compact layout" in settings_js
    assert "Sent once over TLS and never displayed or logged." in settings_js
    # B2 empty-state copy.
    assert "No publications pending" in html
    assert "No write relays configured" in html


async def test_admin_workspace_layout(runtime_env):
    """B1 Linear Split grid — ~390px list desktop, ~320px medium,
    list→detail on ≤560px."""
    resp = await runtime_env["client"].get("/gammamarkets/")
    blocks = re.findall(r"<style>(.*?)</style>", resp.text, re.S)
    css = next(b for b in blocks if ".gm-workspace" in b)
    assert "grid-template-columns: 390px minmax(0, 1fr)" in css
    assert "grid-template-columns: 320px minmax(0, 1fr)" in css
    assert "@media (max-width: 560px)" in css


async def test_admin_no_secrets(runtime_env):
    """The admin document never renders nsec, bearer tokens, full payment
    evidence, or merchant theme tokens."""
    resp = await runtime_env["client"].get("/gammamarkets/")
    html = resp.text
    # The nsec input is masked (password) and its value is never echoed.
    assert 'type="password"' in html
    assert "nsec1" not in html
    # Merchant theme tokens never style the admin shell.
    assert "gm-public {" not in html
    # No full BOLT11/payment-hash rendering surface — technical details
    # use truncated references only (asserted in admin_orders.js too).
    js = (await runtime_env["client"].get(f"{JS}/admin_orders.js")).text
    assert "bolt11" not in js  # never rendered anywhere in admin
    assert "payment_hash" not in js
    # Payment correlation renders only truncated references.
    assert "gmTrunc" in html


async def test_admin_js_legal_actions(runtime_env):
    """The action map only emits legal §7.1/§7.2 transitions."""
    js = (await runtime_env["client"].get(f"{JS}/admin_orders.js")).text
    # Exception branch carries the three resolutions.
    for action in ("accept", "refund", "confirm-refund"):
        assert f'key: "{action}"' in js
    # Shipping transitions are bounded to the §7.2 table targets.
    assert "ship:processing" in js
    assert "ship:shipped" in js
    assert "ship:delivered" in js
    # Token reissue posts to the §5.3 route and shows the link once.
    assert "/public-token/reissue" in js


async def test_admin_publications_copy(runtime_env):
    """B2 — relay ACKs labeled delivery evidence, missing relays named,
    retry only on failed/partial rows."""
    js = (await runtime_env["client"].get(
        f"{JS}/admin_publications.js")).text
    assert "partially_published" in js
    assert "/outbox/" in js and "/retry" in js
    # The outbox state pills cover the full durable vocabulary.
    for state in ("pending", "claimed", "publishing",
                  "partially_published", "failed", "superseded"):
        assert state in js


async def test_admin_notifications_copy(runtime_env):
    """B5 — per-event toggles incl. on_hold, test-send, queue states."""
    js = (await runtime_env["client"].get(
        f"{JS}/admin_notifications.js")).text
    for ev in ("order_received", "confirmed", "on_hold"):
        assert ev in js
    assert "/notifications/test" in js
    assert "Suppressed" in js
    assert "Failed after" in js


async def test_admin_theme_editor(runtime_env):
    """B6 — Tiered Controls: presets, bounded brand basics, opt-in
    advanced tokens, live contrast gate, public-only preview."""
    js = (await runtime_env["client"].get(
        f"{JS}/admin_settings.js")).text
    for preset in ("warm-market", "clean-minimal", "high-contrast"):
        assert preset in js
    assert "advanced_opt_in" in js
    # Client-side WCAG math mirrors the server gate.
    assert "4.5" in js
    assert "contrast" in js
    # Preview tokens resolve client-side (preset → brand → advanced).
    assert "gmPreviewTokens" in js
