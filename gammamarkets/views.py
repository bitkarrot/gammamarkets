"""Generic (non-API) routes: the admin shell page + public storefront.

Mounted under ``/gammamarkets`` by the host via ``gammamarkets_ext``.

Public pages are STANDALONE documents (never the admin ``base.html``):
``no-store``/``no-referrer``, restrictive CSP with no third-party scripts,
``img-src https:`` for merchant images, and theme tokens scoped under
``.gm-public`` only (spec §5.4, UI-SPEC surface A).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

from .services import nip89
from .views_public_api import PUBLIC_HEADERS

gammamarkets_generic_router = APIRouter()

_PUBLIC_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'"
)


def gammamarkets_renderer():
    return template_renderer(["gammamarkets"])


async def _first_images(product_ids: list[str]) -> dict[str, str]:
    """Lowest-sort_order image URL per product — one query for card
    thumbnails on browse pages."""
    if not product_ids:
        return {}
    from .db import db, table

    placeholders = ", ".join(f":p{i}" for i in range(len(product_ids)))
    params = {f"p{i}": pid for i, pid in enumerate(product_ids)}
    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT product_id, url FROM {table('product_images')} "
            f"WHERE product_id IN ({placeholders}) ORDER BY sort_order",
            params,
        )
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(r["product_id"], r["url"])
    return out


def _brand_ctx(merchant: dict | None, theme: dict | None) -> dict:
    """Store-header context (sketch chrome): brand tile + display name.
    Brand Basics name/initials override the merchant display name."""
    brand = (theme or {}).get("brand") or {}
    name = brand.get("name") or (merchant or {}).get("display_name") or ""
    initials = brand.get("initials") or (name[:1].upper() if name else "")
    pubkey = (merchant or {}).get("pubkey")
    return {
        "brand_name": name,
        "brand_initials": initials,
        "storefront_url": (
            f"/gammamarkets/public/merchants/{pubkey}" if pubkey else ""
        ),
    }


def _public_response(request: Request, template: str, ctx: dict,
                   status: int = 200) -> HTMLResponse:
    ctx.setdefault("theme_css", "")
    ctx.setdefault("layout", "editorial")
    resp = gammamarkets_renderer().TemplateResponse(
        request, f"templates/gammamarkets/{template}", ctx,
        status_code=status,
    )
    for k, v in PUBLIC_HEADERS.items():
        resp.headers[k] = v
    resp.headers["Content-Security-Policy"] = _PUBLIC_CSP
    return resp


async def _public_guard(request: Request) -> HTMLResponse | None:
    """Rate-limit public pages; a 429 renders honestly, never a 500."""
    from .security import ProblemError

    try:
        await nip89.check_public_rate_limit(request, bucket="public-page")
    except ProblemError as exc:
        return _public_response(
            request, "public_invalid.html",
            {"message": exc.title}, status=exc.status,
        )
    return None


@gammamarkets_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return gammamarkets_renderer().TemplateResponse(
        request,
        "templates/gammamarkets/admin.html",
        {
            # base.html does JSON.parse({{ user | tojson }}) — it needs the
            # user as a JSON STRING (host convention, see
            # lnbits/core/views/generic.py), not a dict.
            "user": user.json(),
        },
    )


# --- NIP-89 handler + public storefront (spec section 5.4) -----------------------


@gammamarkets_generic_router.get("/p/{naddr}", response_class=HTMLResponse)
async def nip89_handler(request: Request, naddr: str):
    """NIP-89 naddr -> canonical local product page. Relay hints are
    parsed but NEVER fetched (T-202-06) — resolution is local only."""
    limited = await _public_guard(request)
    if limited is not None:
        return limited
    from .security import ProblemError

    try:
        pubkey, d_tag = nip89.decode_product_naddr(naddr)
    except ProblemError:
        return _public_response(request, "public_invalid.html", {},
                                status=404)
    product = await nip89.product_by_address(pubkey, d_tag)
    if not product:
        return _public_response(request, "public_invalid.html", {},
                                status=404)
    resp = RedirectResponse(
        f"/gammamarkets/p/{pubkey}/{d_tag}", status_code=301
    )
    for k, v in PUBLIC_HEADERS.items():
        resp.headers[k] = v
    return resp


@gammamarkets_generic_router.get(
    "/p/{pubkey}/{d_tag}", response_class=HTMLResponse
)
async def product_page(request: Request, pubkey: str, d_tag: str):
    """A1 product page — all documented states per UI-SPEC."""
    limited = await _public_guard(request)
    if limited is not None:
        return limited
    product = await nip89.product_by_address(pubkey, d_tag)
    if not product:
        return _public_response(request, "public_invalid.html", {},
                                status=404)
    detail = await nip89.product_detail(product)
    state = nip89.availability_state(product)
    from .services import themes as theme_service

    theme = await theme_service.get_theme(product["_merchant"]["id"])
    if state in ("unavailable", "hidden", "inactive"):
        return _public_response(
            request, "public_unavailable.html",
            {"state": state}, status=404 if state == "unavailable" else 200,
        )
    return _public_response(
        request,
        "public_product.html",
        {
            "product": nip89.public_product_json(product, detail),
            "state": state,
            "description_html": nip89.render_markdown(
                product.get("description_md")
            ),
            "merchant_name": product["_merchant"].get("display_name") or "",
            "merchant_pubkey": pubkey,
            "theme_css": theme_service.emit_css(theme),
            "layout": theme_service.theme_layout(theme),
            **_brand_ctx(product["_merchant"], theme),
        },
    )


@gammamarkets_generic_router.get(
    "/public/collections/{pubkey}/{d_tag}", response_class=HTMLResponse
)
async def collection_page(request: Request, pubkey: str, d_tag: str):
    limited = await _public_guard(request)
    if limited is not None:
        return limited
    merchant = await nip89.merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] in ("deactivating", "inactive"):
        return _public_response(request, "public_invalid.html", {},
                                status=404)
    from .db import db, table

    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('collections')} "
            "WHERE merchant_id = :m AND d_tag = :d AND deleted_at IS NULL",
            {"m": merchant["id"], "d": d_tag},
        )
        if not row:
            return _public_response(request, "public_invalid.html", {},
                                    status=404)
        members = await conn.fetchall(
            f"SELECT p.* FROM {table('products')} p "
            f"JOIN {table('product_collections')} pc ON pc.product_id = p.id "
            "WHERE pc.collection_id = :c AND p.deleted_at IS NULL"
            " AND NOT p.draft AND p.visibility != 'hidden'",
            {"c": row["id"]},
        )
    member_dicts = [dict(m) | {"_merchant": merchant} for m in members]
    from .services import themes as theme_service

    collection = nip89.collection_json(dict(row), member_dicts)
    images = await _first_images([m["id"] for m in members])
    for prod, member in zip(collection["products"], member_dicts):
        prod["image"] = images.get(member["id"])
    theme = await theme_service.get_theme(merchant["id"])
    return _public_response(
        request,
        "public_collection.html",
        {
            "collection": collection,
            "merchant_pubkey": pubkey,
            "merchant_name": merchant.get("display_name") or "",
            "theme_css": theme_service.emit_css(theme),
            "layout": theme_service.theme_layout(theme),
            **_brand_ctx(merchant, theme),
        },
    )


@gammamarkets_generic_router.get(
    "/public/merchants/{pubkey}", response_class=HTMLResponse
)
async def merchant_page(request: Request, pubkey: str):
    limited = await _public_guard(request)
    if limited is not None:
        return limited
    merchant = await nip89.merchant_by_pubkey(pubkey)
    if not merchant or merchant["state"] in ("deactivating", "inactive"):
        return _public_response(request, "public_invalid.html", {},
                                status=404)
    profile = (
        json.loads(merchant["profile_json"]) if merchant["profile_json"] else {}
    )
    from .db import db, table

    async with db.connect() as conn:
        products = await conn.fetchall(
            f"SELECT * FROM {table('products')} "
            "WHERE merchant_id = :m AND deleted_at IS NULL AND NOT draft"
            " AND parent_product_id IS NULL AND visibility != 'hidden'"
            " ORDER BY created_at",
            {"m": merchant["id"]},
        )
        # Storefront index lists only collections with at least one
        # visible member — zero-member collections are never rendered
        # (they are unpublishable by contract).
        collections = await conn.fetchall(
            f"SELECT c.* FROM {table('collections')} c "
            "WHERE c.merchant_id = :m AND c.deleted_at IS NULL"
            " AND EXISTS ("
            f"SELECT 1 FROM {table('product_collections')} pc "
            f"JOIN {table('products')} p ON p.id = pc.product_id "
            "WHERE pc.collection_id = c.id AND p.deleted_at IS NULL"
            " AND NOT p.draft AND p.visibility != 'hidden'"
            ") ORDER BY c.title",
            {"m": merchant["id"]},
        )
    images = await _first_images([p["id"] for p in products])
    cards = [
        {
            "d_tag": p["d_tag"],
            "title": p["title"] or "",
            "amount_minor": p["amount_minor"],
            "currency": p["currency"],
            "currency_decimals": p["currency_decimals"],
            "image": images.get(p["id"]),
            "availability": nip89.availability_state(
                dict(p) | {"_merchant": merchant}
            ),
        }
        for p in products
    ]
    from .services import themes as theme_service

    theme = await theme_service.get_theme(merchant["id"])
    return _public_response(
        request,
        "public_merchant.html",
        {
            "pubkey": merchant["pubkey"],
            "display_name": merchant.get("display_name") or "",
            "about": profile.get("about", ""),
            "picture": profile.get("picture"),
            "products": cards,
            "collections": [
                {
                    "d_tag": c["d_tag"],
                    "title": c["title"] or "",
                    "description": c["description"] or "",
                }
                for c in collections
            ],
            "theme_css": theme_service.emit_css(theme),
            **_brand_ctx(merchant, theme),
        },
    )


@gammamarkets_generic_router.get("/order", response_class=HTMLResponse)
async def order_page(request: Request):
    """A3 order-status document shell — the bearer token arrives only as a
    URL fragment (never sent to the server); JS strips it immediately and
    sends it as ``X-Order-Token``. Status polling lands in 02-03/02-04."""
    limited = await _public_guard(request)
    if limited is not None:
        return limited
    return _public_response(request, "public_order.html", {})
