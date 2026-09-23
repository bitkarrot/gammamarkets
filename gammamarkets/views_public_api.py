"""Public read-only JSON API — spec section 5.4.

Unauthenticated, database rate-limited (120 GET/min per HMAC'd IP scope —
raw IPs never persist), ``no-store``/``no-referrer`` on every response,
and the payload contract carries no merchant internals, internal ids,
buyer echoes, or bearer tokens.
"""

from __future__ import annotations

import functools
import json
import time

from fastapi import APIRouter, Request, Response

from . import crypto
from .db import db, table
from .security import ProblemError, not_found, problem_for
from .services import checkout as checkout_service
from .services import nip89, readiness
from .settings import ext_settings

gammamarkets_public_api_router = APIRouter(prefix="/api/v1/public")

PUBLIC_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def public_boundary(fn):
    """RFC 9457 mapping WITHOUT admin mutation enforcement — public
    routes are anonymous by design (buyers never authenticate), so the
    cookie/bearer CSRF rules of ``problem_boundary`` must not apply.

    Problem responses still carry the section-5.4 protective headers —
    the injected ``Response`` is bypassed when a ProblemError becomes a
    fresh JSONResponse, so they are stamped here too."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ProblemError as exc:
            resp = problem_for(exc)
            for k, v in PUBLIC_HEADERS.items():
                resp.headers[k] = v
            return resp

    return wrapper


async def _guard(request: Request, response: Response) -> None:
    await nip89.check_public_rate_limit(request)
    for k, v in PUBLIC_HEADERS.items():
        response.headers[k] = v


@gammamarkets_public_api_router.get("/merchants/{pubkey}")
@public_boundary
async def public_merchant(pubkey: str, request: Request, response: Response):
    await _guard(request, response)
    merchant = await nip89.merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] in ("deactivating", "inactive"):
        raise not_found("merchant not found")
    profile = (
        json.loads(merchant["profile_json"]) if merchant["profile_json"] else {}
    )
    return {
        "pubkey": merchant["pubkey"],
        "display_name": merchant["display_name"] or "",
        "profile": {
            k: v
            for k, v in profile.items()
            if k in ("about", "website", "picture", "banner", "nip05")
        },
        "state": "active" if merchant["state"] == "active" else "draft",
    }


@gammamarkets_public_api_router.get("/products/{pubkey}/{d_tag}")
@public_boundary
async def public_product(
    pubkey: str, d_tag: str, request: Request, response: Response
):
    await _guard(request, response)
    product = await nip89.product_by_address(pubkey, d_tag)
    if not product:
        raise not_found("product not found")
    detail = await nip89.product_detail(product)
    return nip89.public_product_json(product, detail)


@gammamarkets_public_api_router.get("/collections/{pubkey}/{d_tag}")
@public_boundary
async def public_collection(
    pubkey: str, d_tag: str, request: Request, response: Response
):
    await _guard(request, response)
    merchant = await nip89.merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] in ("deactivating", "inactive"):
        raise not_found("collection not found")
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('collections')} "
            "WHERE merchant_id = :m AND d_tag = :d AND deleted_at IS NULL",
            {"m": merchant["id"], "d": d_tag},
        )
        if not row:
            raise not_found("collection not found")
        members = await conn.fetchall(
            f"SELECT p.* FROM {table('products')} p "
            f"JOIN {table('product_collections')} pc ON pc.product_id = p.id "
            "WHERE pc.collection_id = :c AND p.deleted_at IS NULL"
            " AND NOT p.draft AND p.visibility != 'hidden'",
            {"c": row["id"]},
        )
    member_dicts = []
    for m in members:
        md = dict(m)
        md["_merchant"] = merchant
        member_dicts.append(md)
    return nip89.collection_json(dict(row), member_dicts)


@gammamarkets_public_api_router.get("/shipping/{pubkey}/{d_tag}")
@public_boundary
async def public_shipping(
    pubkey: str, d_tag: str, request: Request, response: Response
):
    await _guard(request, response)
    merchant = await nip89.merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] in ("deactivating", "inactive"):
        raise not_found("shipping option not found")
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('shipping_options')} "
            "WHERE merchant_id = :m AND d_tag = :d AND deleted_at IS NULL"
            " AND active",
            {"m": merchant["id"], "d": d_tag},
        )
    if not row:
        raise not_found("shipping option not found")
    row = dict(row)
    return {
        "d_tag": row["d_tag"],
        "title": row["title"] or "",
        "base_price_minor": row["base_price_minor"],
        "currency": row["currency"],
        "service": row["service"],
        "countries": json.loads(row["countries"]) if row["countries"] else [],
        "regions": json.loads(row["regions"]) if row["regions"] else [],
        "duration_min": row["duration_min"],
        "duration_max": row["duration_max"],
        "duration_unit": row["duration_unit"],
    }


# --- section 5.4 checkout / order-status / opt-out -----------------------------


def _client_scope(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@gammamarkets_public_api_router.post("/checkout", status_code=201)
@public_boundary
async def public_checkout(request: Request, response: Response, body: dict):
    """§5.4 checkout — idempotency-claimed intake + §8.2 saga.

    Both checkout rate windows (10/min + 100/hour per HMAC'd IP) apply
    BEFORE the idempotency claim so replays also count toward the cap.
    """
    await _guard(request, response)
    readiness.assert_checkout_ready()
    settings = ext_settings()
    scope = _client_scope(request)
    # §15: both checkout windows — 10/min AND 100/hour per IP.
    await nip89.check_public_rate_limit(
        request, bucket="checkout-min",
        limit=settings.checkout_rate_limit, window_s=60,
    )
    await nip89.check_public_rate_limit(
        request, bucket="checkout-hour",
        limit=settings.checkout_rate_limit_hourly, window_s=3600,
    )
    key = checkout_service.validate_idempotency_key(
        request.headers.get("idempotency-key")
    )
    return await checkout_service.checkout(
        payload=body, idempotency_key=key, client_scope=scope,
    )


_TOKEN_INVALID = ProblemError(
    401, "unauthorized", "Token invalid",
    "this order link is no longer valid",
)


async def _order_for_token(token: str | None) -> dict:
    """Resolve the order by bearer token — identical failure for every
    invalid shape (no existence oracle, §11.4/§5.4)."""
    if not token:
        raise _TOKEN_INVALID
    try:
        digest = crypto.token_lookup_hash(token)
    except crypto.CryptoError:
        raise _TOKEN_INVALID from None
    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('orders')} "
            "WHERE public_token_hash = :h",
            {"h": digest},
        )
    if not row:
        raise _TOKEN_INVALID
    order = dict(row)
    now = int(time.time())
    if (
        order["public_token_expires_at"] is not None
        and order["public_token_expires_at"] <= now
    ):
        raise _TOKEN_INVALID
    return order


@gammamarkets_public_api_router.get("/order-status")
@public_boundary
async def public_order_status(request: Request, response: Response):
    """§5.4 status — token arrives ONLY via the X-Order-Token header.

    The response is restricted to exactly the §5.4 field set: state,
    shipping_state, total_sat, bolt11 (while awaiting_payment), payment
    status, item summaries, and expiry. No internals, no payment_hash,
    no buyer echoes.
    """
    await _guard(request, response)
    order = await _order_for_token(request.headers.get("x-order-token"))
    async with db.connect() as conn:
        items = await conn.fetchall(
            f"SELECT title, quantity, line_total_sat FROM"
            f" {table('order_items')} WHERE order_id = :o",
            {"o": order["id"]},
        )
        payment = await conn.fetchone(
            f"SELECT status, bolt11_enc FROM {table('payments')} "
            "WHERE order_id = :o",
            {"o": order["id"]},
        )
    bolt11 = None
    if (
        order["state"] == "awaiting_payment"
        and payment
        and payment["bolt11_enc"] is not None
    ):
        settings = ext_settings()
        ver = crypto.envelope_version(payment["bolt11_enc"])
        bolt11 = crypto.decrypt(
            payment["bolt11_enc"], settings.master_keys[ver],
            record_id=order["id"], table="payments", column="bolt11_enc",
            key_version=ver,
        ).decode()
    return {
        "state": order["state"],
        "shipping_state": order["shipping_state"],
        "total_sat": order["total_sat"],
        "bolt11": bolt11,
        "payment_status": payment["status"] if payment else None,
        "items": [
            {"title": i["title"], "quantity": i["quantity"],
             "line_total_sat": i["line_total_sat"]}
            for i in items
        ],
        "expires_at": order["invoice_expiry"],
        "email_opt_in": bool(order["email_opt_in"]),
        # Buyer-safe hold flag — drives the "On hold — the merchant is
        # reviewing a payment issue." label (never the reason detail).
        "payment_exception": bool(order["payment_exception"]),
    }


@gammamarkets_public_api_router.post("/order-email-opt-out")
@public_boundary
async def public_order_email_opt_out(request: Request, response: Response):
    """§8.8 opt-out — sets email_opt_in=false and cancels queued customer
    rows for the order (never a signal beyond the bearer token)."""
    await _guard(request, response)
    order = await _order_for_token(request.headers.get("x-order-token"))
    from .db import DomainTransaction

    async with DomainTransaction() as tx:
        await tx.execute(
            f"UPDATE {tx.table('orders')} SET email_opt_in = FALSE,"
            " public_token_enc = NULL, updated_at = :n WHERE id = :i",
            {"n": int(time.time()), "i": order["id"]},
        )
        await tx.execute(
            f"UPDATE {tx.table('email_queue')} SET state = 'suppressed'"
            " WHERE order_id = :o AND channel = 'customer'"
            " AND state IN ('pending', 'claimed')",
            {"o": order["id"]},
        )
    return {"email_opt_in": False}
