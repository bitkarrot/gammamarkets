"""Public read-only JSON API — spec section 5.4.

Unauthenticated, database rate-limited (120 GET/min per HMAC'd IP scope —
raw IPs never persist), ``no-store``/``no-referrer`` on every response,
and the payload contract carries no merchant internals, internal ids,
buyer echoes, or bearer tokens.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from .db import db, table
from .security import not_found
from .services import nip89
from .views_api import problem_boundary

gammamarkets_public_api_router = APIRouter(prefix="/api/v1/public")

PUBLIC_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


async def _guard(request: Request, response: Response) -> None:
    await nip89.check_public_rate_limit(request)
    for k, v in PUBLIC_HEADERS.items():
        response.headers[k] = v


@gammamarkets_public_api_router.get("/merchants/{pubkey}")
@problem_boundary
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
@problem_boundary
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
@problem_boundary
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
@problem_boundary
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
