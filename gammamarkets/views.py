"""Generic (non-API) routes: the admin shell page.

Mounted under ``/gammamarkets`` by the host via ``gammamarkets_ext``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

gammamarkets_generic_router = APIRouter()


def gammamarkets_renderer():
    return template_renderer(["gammamarkets"])


@gammamarkets_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return gammamarkets_renderer().TemplateResponse(
        request,
        "templates/gammamarkets/index.html",
        {
            # pydantic's own encoder first: UUID/datetime values inside
            # user.dict() break the host's globally patched JSONEncoder.
            "user": json.loads(user.json()),
        },
    )
