"""Launch a real LNbits + gammamarkets server for Playwright E2E.

Boots the pinned host through uvicorn with the same posture as the
runtime suite (FakeWallet, extension symlinked into a tmp
LNBITS_EXTENSIONS_PATH, GAMMAMARKETS_* env, relay IO off), seeds an
account/wallet/merchant/catalog/products + one live order via the real
HTTP APIs, then serves until killed.

Two harness-only routes are registered on the app AFTER startup —
``/_e2e/settle`` (pays the order's invoice through FakeWallet and runs
the same settlement calls the listener makes) and ``/_e2e/seed`` (the
seed JSON the Playwright specs read). Neither touches shipped code.

    uv run python tools/e2e_server.py          # http://127.0.0.1:5099
    GM_E2E_PORT=5200 uv run python tools/e2e_server.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "gammamarkets"
sys.path.insert(0, str(REPO_ROOT))

PORT = int(os.environ.get("GM_E2E_PORT", "5099"))
# Served over HTTPS so the real browser satisfies the §5.1 invariant
# (cookie mutations require Origin == GAMMAMARKETS_PUBLIC_BASE_URL, and
# that setting must be an https:// origin). A throwaway self-signed cert
# is generated per run; the seed client + Playwright ignore verification.
BASE_URL = f"https://localhost:{PORT}"
SEED_PATH = REPO_ROOT / "tests" / "e2e" / ".seed.json"

# Fixed merchant identity so public URLs are stable across server
# restarts (test-only key — the E2E database is disposable).
E2E_NSEC = (
    "nsec1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqstywftw"
)
E2E_PUBKEY = (
    "1b84c5567b126440995d3ed5aaba0565d71e1834604819ff9c17f5e9d5dd078f"
)

# All environment must be set BEFORE any lnbits import — `settings` and
# `lnbits.core.db.db` bind these values at construction. Setting them as
# attributes later leaves the core DB bound to ./data (repo root), which
# carries stale install/deactivation state across runs.
TMP = Path(tempfile.mkdtemp(prefix="gm-e2e-"))
EXT_DIR = TMP / "extroot" / "extensions"
DATA_DIR = TMP / "data"
EXT_DIR.mkdir(parents=True)
(EXT_DIR / "gammamarkets").symlink_to(PKG_DIR, target_is_directory=True)
DATA_DIR.mkdir()

os.environ.update(
    {
        "GAMMAMARKETS_MASTER_KEYS": json.dumps(
            {"v1": base64.b64encode(b"k" * 32).decode()}
        ),
        "GAMMAMARKETS_ACTIVE_KEY_VERSION": "v1",
        "GAMMAMARKETS_PRIVACY_KEY": base64.b64encode(b"p" * 32).decode(),
        "GAMMAMARKETS_PUBLIC_BASE_URL": BASE_URL,
        "GAMMAMARKETS_RELAY_IO": "off",
        # Host settings via env so they are in place at settings/db
        # construction — not just attribute assignment after the fact.
        "LNBITS_DATA_FOLDER": str(DATA_DIR),
        "LNBITS_EXTENSIONS_PATH": str(TMP / "extroot"),
        "LNBITS_EXTENSIONS_DEACTIVATE_ALL": "false",
        "LNBITS_BACKEND_WALLET_CLASS": "FakeWallet",
        "LNBITS_ADMIN_UI": "true",
        "LNBITS_AUDIT_LOG_REQUEST_BODY": "false",
        "LNBITS_AUDIT_LOG_QUERY_PARAMS": "false",
        "LNBITS_AUDIT_LOG_PATH_PARAMS": "false",
        "FIRST_INSTALL": "true",
    }
)


async def _seed(app, seed: dict) -> None:
    """Create account/wallet/merchant/catalog/products/order through the
    same paths the runtime suite uses."""
    import httpx
    from lnbits.core.crud import create_wallet
    from lnbits.core.crud.users import create_account
    from lnbits.core.models.users import (
        Account,
        UpdateSuperuserPassword,
    )
    from lnbits.core.services import update_wallet_balance
    from lnbits.core.views.auth_api import first_install
    from lnbits.settings import settings

    # First install gates the auth API — create the superuser through the
    # host's own path (same as the runtime conftest).
    superuser = f"gqadmin-{uuid.uuid4().hex[:8]}"
    await first_install(
        UpdateSuperuserPassword(
            username=superuser,
            password="secret1234",
            password_repeat="secret1234",
            first_install_token=settings.first_install_token,
        )
    )

    # Fixed credentials so a human can log into the browser session —
    # local E2E only, never reused (fresh tmp DB per run).
    username = "admin"
    password = "adminpass123"
    account = Account(id=uuid.uuid4().hex, username=username, email=None)
    account.hash_password(password)
    await create_account(account)
    wallet = await create_wallet(user_id=account.id, wallet_name="e2e")
    await update_wallet_balance(wallet=wallet, amount=9_999_999)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=BASE_URL,
        verify=False,
    ) as client:
        resp = await client.post(
            "/api/v1/auth",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        # Cookie in the jar (not a raw header) so httpx merges it with the
        # gm_csrf cookie the admin API issues — a hand-set Cookie header
        # would suppress jar cookies and fail the double-submit check.
        client.cookies.set(
            "cookie_access_token", token, domain="localhost", path="/"
        )
        resp = await client.put(
            "/api/v1/extension/gammamarkets/enable",
            headers={"Origin": BASE_URL},
        )
        assert resp.status_code == 200, resp.text

        api = "/gammamarkets/api/v1"

        async def cookie() -> dict:
            if not client.cookies.get("gm_csrf"):
                await client.get(
                    f"{api}/merchants/current", headers={"Origin": BASE_URL}
                )
            return {
                "Origin": BASE_URL,
                "X-CSRF-Token": client.cookies.get("gm_csrf"),
            }

        resp = await client.post(
            f"{api}/merchants",
            json={"wallet_id": wallet.id, "display_name": "e2e shop"},
            headers=await cookie(),
        )
        assert resp.status_code == 201, resp.text
        mid = resp.json()["id"]

        from gammamarkets.db import DomainTransaction
        from gammamarkets.services import merchant as merchant_service
        from gammamarkets.services import relay as relay_service

        # A merchant that reached `active` through publish would have the
        # starter relay set — seed it directly (RELAY_IO=off, no publish).
        await relay_service.ensure_default_relays(mid)

        # Fixed test identity so storefront/product URLs are STABLE across
        # restarts (key material is test-only; the seed DB is disposable).
        await merchant_service.import_nsec(mid, account, E2E_NSEC)

        async with DomainTransaction() as tx:
            await tx.execute(
                "UPDATE merchants SET state = 'active' WHERE id = :m",
                {"m": mid},
            )
            merchant = await tx.fetch_one(
                "SELECT pubkey FROM merchants WHERE id = :m", {"m": mid}
            )
        pubkey = merchant["pubkey"]

        resp = await client.post(
            f"{api}/catalogs",
            json={"name": "main", "default_currency": "SAT"},
            headers=await cookie(),
        )
        cid = resp.json()["id"]

        resp = await client.post(
            f"{api}/products",
            json={
                "catalog_id": cid,
                "d_tag": "e2e-digital-tour",
                "title": "e2e digital tour",
                "amount_minor": 2500,
                "currency": "SAT",
                "visibility": "on-sale",
                "stock_on_hand": 10,
                "format": "digital",
            },
            headers=await cookie(),
        )
        digital = resp.json()

        resp = await client.post(
            f"{api}/shipping",
            json={
                "title": "Standard mail",
                "service": "standard",
                "countries": ["US", "DE"],
                "base_price_minor": 500,
                "currency": "SAT",
            },
            headers=await cookie(),
        )
        assert resp.status_code == 201, resp.text
        shipping = resp.json()

        resp = await client.post(
            f"{api}/products",
            json={
                "catalog_id": cid,
                "d_tag": "e2e-poster",
                "title": "e2e poster",
                "amount_minor": 7500,
                "currency": "SAT",
                "visibility": "on-sale",
                "stock_on_hand": 5,
                "format": "physical",
                "shipping_option_ids": [shipping["id"]],
            },
            headers=await cookie(),
        )
        assert resp.status_code == 201, resp.text
        physical = resp.json()

        # One live order so the admin Orders tab has a row on load.
        resp = await client.post(
            f"{api}/public/checkout",
            json={
                "merchant_pubkey": pubkey,
                "items": [{"d_tag": digital["d_tag"], "quantity": 1}],
            },
            headers={
                "Idempotency-Key": uuid.uuid4().hex * 2,
                "Origin": BASE_URL,
            },
        )
        assert resp.status_code == 201, resp.text
        order = resp.json()

    from gammamarkets.services import readiness

    readiness.mark_reconciled()

    seed.update(
        {
            "base_url": BASE_URL,
            "username": username,
            "password": password,
            "access_token": token,
            "merchant_id": mid,
            "pubkey": pubkey,
            "digital": digital,
            "physical": physical,
            "shipping": shipping,
            "seeded_order_token": order["public_token"],
            "digital_url": f"{BASE_URL}/gammamarkets/p/{pubkey}/{digital['d_tag']}",
            "physical_url": f"{BASE_URL}/gammamarkets/p/{pubkey}/{physical['d_tag']}",
        }
    )


async def _settle(token: str) -> dict:
    """Pay the order's core invoice via FakeWallet and run the listener
    path — the same calls the paid-invoices stream consumer makes."""
    from lnbits.core.db import db as core_db
    from lnbits.core.services.payments import (
        update_invoice_from_paid_invoices_stream,
    )
    from lnbits.wallets import get_funding_source

    from gammamarkets.crypto import token_lookup_hash
    from gammamarkets.db import db

    async with db.connect() as conn:
        row = await conn.fetchone(
            "SELECT * FROM gammamarkets.orders WHERE public_token_hash = :h",
            {"h": token_lookup_hash(token)},
        )
    if row is None:
        return {"ok": False, "error": "unknown token"}
    order = dict(row)

    async with core_db.connect() as conn:
        core = dict(
            await conn.fetchone(
                "SELECT * FROM apipayments WHERE external_id = :e",
                {"e": f"gammamarkets:{order['id']}"},
            )
        )
    funding = get_funding_source()
    resp = await funding.pay_invoice(core["bolt11"], fee_limit_msat=10_000)
    if not resp.ok:
        return {"ok": False, "error": resp.error_message}
    settled = await update_invoice_from_paid_invoices_stream(
        core["checking_id"]
    )
    assert settled is not None

    from gammamarkets.services.settlement import (
        _core_payments_by_external_id,  # noqa: SLF001
        invoice_listener,
    )

    payments = await _core_payments_by_external_id(
        f"gammamarkets:{order['id']}"
    )
    await invoice_listener(payments[0])
    return {"ok": True, "order_id": order["id"]}


async def main() -> None:
    from lnbits.settings import settings

    from tools.checkout_host import host_checkout_dir

    settings.first_install = True

    cert = TMP / "e2e.pem"
    key = TMP / "e2e-key.pem"
    import subprocess

    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )

    os.chdir(host_checkout_dir())
    from lnbits.app import create_app

    app = create_app()

    seed: dict = {}

    from fastapi import Query

    async def e2e_seed():
        return seed

    async def e2e_settle(token: str = Query(...)):
        return await _settle(token)

    app.add_api_route("/_e2e/seed", e2e_seed, methods=["GET"])
    app.add_api_route("/_e2e/settle", e2e_settle, methods=["POST"])

    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
        )
    )
    serve = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
        if serve.done():
            raise serve.exception()  # type: ignore[misc]

    import importlib

    from lnbits.app import check_and_register_extensions

    ext_module = importlib.import_module("gammamarkets")
    if ext_module.started_at is None:
        await check_and_register_extensions(app)

    await _seed(app, seed)
    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_PATH.write_text(json.dumps(seed, indent=2))
    print(f"e2e server ready at {BASE_URL} — seed -> {SEED_PATH}")

    await serve


if __name__ == "__main__":
    asyncio.run(main())
