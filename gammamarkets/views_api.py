"""Admin JSON API — /gammamarkets/api/v1 (spec section 5.1/5.6).

Every route depends on the section-5.1 guard: ``check_user_exists`` for
identity, plus mutation rules (user-id-only rejected; cookie auth requires
exact canonical Origin + double-submit CSRF; bearer passes). All failures
are RFC 9457 problem details.
"""

from __future__ import annotations

import functools
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from pydantic import BaseModel, Field

from .security import (
    ProblemError,
    enforce_mutation_security,
    issue_csrf_cookie,
    problem_for,
    unprocessable,
)
from .services import merchant as merchant_service

gammamarkets_api_router = APIRouter(prefix="/api/v1")


def problem_boundary(fn):
    """Enforce section-5.1 mutation security + render ProblemError as
    problem+json.

    Every route declares ``request: Request`` so this wrapper can run the
    mutation rules (dependency-raised errors would bypass problem+json
    rendering). Routes also declaring ``response: Response`` get the
    double-submit CSRF cookie issued for cookie-authenticated callers —
    on BOTH success and problem paths, so a fresh admin client (whose
    first call may 404) always receives a token.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        request = kwargs.get("request")
        response = kwargs.get("response")
        try:
            if isinstance(request, Request):
                enforce_mutation_security(request)
            result = await fn(*args, **kwargs)
        except ProblemError as exc:
            resp = problem_for(exc)
            if isinstance(request, Request) and request.cookies.get(
                "cookie_access_token"
            ):
                issue_csrf_cookie(resp, request)
            return resp
        if (
            isinstance(request, Request)
            and isinstance(response, Response)
            and request.cookies.get("cookie_access_token")
        ):
            issue_csrf_cookie(response, request)
        return result

    return wrapper


# --- request bodies ----------------------------------------------------------


class _Strict(BaseModel):
    class Config:
        extra = "forbid"


class CreateMerchantBody(_Strict):
    wallet_id: str
    display_name: str | None = None
    payment_preference: str = "manual"


class PatchMerchantBody(_Strict):
    display_name: str | None = None
    profile_json: Any = None
    recommended_app_d: str | None = None
    wallet_id: str | None = None
    notify_emails: list[str] | None = None
    notify_events: dict | None = None
    theme: Any = None
    relay_configs: list[dict] | None = None


class ImportKeyBody(_Strict):
    nsec: str = Field(min_length=1, max_length=128)


class TestNotificationBody(_Strict):
    recipient: str


class PatchNotificationsBody(_Strict):
    notify_emails: list[str] | None = None
    notify_events: dict | None = None


def _patch_dict(body: PatchMerchantBody) -> dict:
    """Only fields explicitly present in the request are patched."""
    return {
        k: v for k, v in body.dict(exclude_unset=True).items()
        if v is not None or k in body.__fields_set__
    }


# --- section 5.1 merchant routes ---------------------------------------------


@gammamarkets_api_router.post("/merchants", status_code=201)
@problem_boundary
async def create_merchant(
    request: Request,
    body: CreateMerchantBody, user: User = Depends(check_user_exists)
):
    return await merchant_service.create_merchant(
        user,
        wallet_id=body.wallet_id,
        display_name=body.display_name,
        payment_preference=body.payment_preference,
    )


@gammamarkets_api_router.get("/merchants/current")
@problem_boundary
async def get_current_merchant(
    request: Request,
    response: Response,
    user: User = Depends(check_user_exists),
):
    # Admin clients learn the double-submit token via the boundary before
    # mutating — even when this GET 404s on a first visit.
    return await merchant_service.current_merchant(user)


@gammamarkets_api_router.patch("/merchants/{merchant_id}")
@problem_boundary
async def patch_merchant(
    request: Request,
    merchant_id: str,
    body: PatchMerchantBody,
    user: User = Depends(check_user_exists),
):
    return await merchant_service.patch_merchant(
        merchant_id, user, _patch_dict(body)
    )


@gammamarkets_api_router.post("/merchants/{merchant_id}/keys/import")
@problem_boundary
async def import_key(
    request: Request,
    merchant_id: str,
    body: ImportKeyBody,
    user: User = Depends(check_user_exists),
):
    merchant = await merchant_service.import_nsec(
        merchant_id, user, body.nsec
    )
    # The nsec never appears in the response (or anywhere outside the
    # keystore operation).
    return {"pubkey": merchant["pubkey"], "merchant_id": merchant["id"]}


@gammamarkets_api_router.post("/merchants/{merchant_id}/publish")
@problem_boundary
async def publish_merchant(
    request: Request,
    merchant_id: str, user: User = Depends(check_user_exists)
):
    return await merchant_service.publish(merchant_id, user)


@gammamarkets_api_router.get("/merchants/{merchant_id}/relay-health")
@problem_boundary
async def get_relay_health(
    request: Request,
    merchant_id: str, user: User = Depends(check_user_exists)
):
    return await merchant_service.relay_health(merchant_id, str(user.id))


@gammamarkets_api_router.get("/merchants/{merchant_id}/notifications")
@problem_boundary
async def get_notifications(
    request: Request,
    merchant_id: str, user: User = Depends(check_user_exists)
):
    return await merchant_service.get_notifications(merchant_id, user)


@gammamarkets_api_router.patch("/merchants/{merchant_id}/notifications")
@problem_boundary
async def patch_notifications(
    request: Request,
    merchant_id: str,
    body: PatchNotificationsBody,
    user: User = Depends(check_user_exists),
):
    patch = {
        k: v for k, v in body.dict(exclude_unset=True).items()
    }
    if not patch:
        raise unprocessable(
            "invalid-transition", "Empty notification patch"
        )
    return await merchant_service.patch_merchant(
        merchant_id, user, patch
    )


@gammamarkets_api_router.post("/merchants/{merchant_id}/notifications/test")
@problem_boundary
async def test_notification(
    request: Request,
    merchant_id: str,
    body: TestNotificationBody,
    user: User = Depends(check_user_exists),
):
    return await merchant_service.send_test_notification(
        merchant_id, user, body.recipient
    )


@gammamarkets_api_router.delete("/merchants/{merchant_id}")
@problem_boundary
async def delete_merchant(
    request: Request,
    merchant_id: str, user: User = Depends(check_user_exists)
):
    return await merchant_service.begin_deactivation(merchant_id, user)


# --- section 5.2 catalog routes ---------------------------------------------------
#
# These paths carry no merchant id — the caller's 1:1 merchant resolves
# implicitly (POST /merchants is the only way to create one).

from .services import catalog as catalog_service  # noqa: E402


async def _mid(user) -> str:
    return (await merchant_service.current_merchant(user))["id"]


@gammamarkets_api_router.post("/catalogs", status_code=201)
@problem_boundary
async def create_catalog(
    request: Request,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.create_catalog(await _mid(user), user, body)


@gammamarkets_api_router.get("/catalogs")
@problem_boundary
async def list_catalogs(
    request: Request, user: User = Depends(check_user_exists)
):
    return await catalog_service.list_catalogs(await _mid(user), user)


@gammamarkets_api_router.get("/catalogs/{catalog_id}")
@problem_boundary
async def get_catalog(
    request: Request,
    catalog_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.get_catalog(
        await _mid(user), user, catalog_id
    )


@gammamarkets_api_router.patch("/catalogs/{catalog_id}")
@problem_boundary
async def patch_catalog(
    request: Request,
    catalog_id: str,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.patch_catalog(
        await _mid(user), user, catalog_id, body
    )


@gammamarkets_api_router.delete("/catalogs/{catalog_id}")
@problem_boundary
async def delete_catalog(
    request: Request,
    catalog_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.delete_catalog(
        await _mid(user), user, catalog_id
    )


@gammamarkets_api_router.post("/products", status_code=201)
@problem_boundary
async def create_product(
    request: Request,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.create_product(await _mid(user), user, body)


@gammamarkets_api_router.get("/products")
@problem_boundary
async def list_products(
    request: Request,
    user: User = Depends(check_user_exists),
    catalog_id: str | None = None,
):
    return await catalog_service.list_products(
        await _mid(user), user, catalog_id=catalog_id
    )


@gammamarkets_api_router.get("/products/{product_id}")
@problem_boundary
async def get_product(
    request: Request,
    product_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.get_product(
        await _mid(user), user, product_id
    )


@gammamarkets_api_router.patch("/products/{product_id}")
@problem_boundary
async def patch_product(
    request: Request,
    product_id: str,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.patch_product(
        await _mid(user), user, product_id, body
    )


@gammamarkets_api_router.delete("/products/{product_id}")
@problem_boundary
async def delete_product(
    request: Request,
    product_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.delete_product(
        await _mid(user), user, product_id
    )


@gammamarkets_api_router.post("/products/{product_id}/images",
                              status_code=201)
@problem_boundary
async def add_product_image(
    request: Request,
    product_id: str,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.add_product_image(
        await _mid(user), user, product_id, body
    )


@gammamarkets_api_router.get("/products/{product_id}/events")
@problem_boundary
async def get_product_events(
    request: Request,
    product_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.product_events(
        await _mid(user), user, product_id
    )


@gammamarkets_api_router.post("/collections", status_code=201)
@problem_boundary
async def create_collection(
    request: Request,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.create_collection(
        await _mid(user), user, body
    )


@gammamarkets_api_router.get("/collections")
@problem_boundary
async def list_collections(
    request: Request, user: User = Depends(check_user_exists)
):
    return await catalog_service.list_collections(await _mid(user), user)


@gammamarkets_api_router.get("/collections/{collection_id}")
@problem_boundary
async def get_collection(
    request: Request,
    collection_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.get_collection(
        await _mid(user), user, collection_id
    )


@gammamarkets_api_router.patch("/collections/{collection_id}")
@problem_boundary
async def patch_collection(
    request: Request,
    collection_id: str,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.patch_collection(
        await _mid(user), user, collection_id, body
    )


@gammamarkets_api_router.delete("/collections/{collection_id}")
@problem_boundary
async def delete_collection(
    request: Request,
    collection_id: str,
    user: User = Depends(check_user_exists),
    strip: bool = False,
):
    return await catalog_service.delete_collection(
        await _mid(user), user, collection_id, strip=strip
    )


@gammamarkets_api_router.post("/shipping", status_code=201)
@problem_boundary
async def create_shipping(
    request: Request,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.create_shipping(await _mid(user), user, body)


@gammamarkets_api_router.get("/shipping")
@problem_boundary
async def list_shipping(
    request: Request, user: User = Depends(check_user_exists)
):
    return await catalog_service.list_shipping(await _mid(user), user)


@gammamarkets_api_router.get("/shipping/{option_id}")
@problem_boundary
async def get_shipping(
    request: Request,
    option_id: str,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.get_shipping(
        await _mid(user), user, option_id
    )


@gammamarkets_api_router.patch("/shipping/{option_id}")
@problem_boundary
async def patch_shipping(
    request: Request,
    option_id: str,
    body: dict,
    user: User = Depends(check_user_exists),
):
    return await catalog_service.patch_shipping(
        await _mid(user), user, option_id, body
    )


@gammamarkets_api_router.delete("/shipping/{option_id}")
@problem_boundary
async def delete_shipping(
    request: Request,
    option_id: str,
    user: User = Depends(check_user_exists),
    strip: bool = False,
):
    return await catalog_service.delete_shipping(
        await _mid(user), user, option_id, strip=strip
    )
