"""GammaMarkets — LNbits extension.

NIP-99 catalog publication and Lightning checkout over one authoritative
inventory. Host integration contract (pinned host v1.6.2-rc1, e336fe1):

- ``gammamarkets_ext`` — APIRouter carrying its own ``/gammamarkets`` prefix
  (the host adds none).
- ``gammamarkets_static_files`` — declarative list; the host mounts it.
- ``gammamarkets_start`` — synchronous (host calls it unawaited); does
  bounded registrations only.
- ``gammamarkets_stop`` — cancels exactly the task handles this module owns.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter

from .db import db  # noqa: F401  (host migration runner imports this attr)

gammamarkets_ext: APIRouter = APIRouter(
    prefix="/gammamarkets", tags=["gammamarkets"]
)

gammamarkets_static_files = [
    {"path": "/gammamarkets/static", "name": "gammamarkets_static"},
]

gammamarkets_redirect_paths: list = []

#: Task handles this extension owns — cancelled by gammamarkets_stop.
_owned_tasks: list[asyncio.Task] = []

#: Set when the start hook ran (install test asserts the sync contract).
started_at: int | None = None


def register_owned_task(task: asyncio.Task) -> asyncio.Task:
    """Track an extension-owned task handle for stop-hook cancellation."""
    _owned_tasks.append(task)
    return task


def gammamarkets_start() -> None:
    """Synchronous start hook (host invokes unawaited on restore).

    Strict ``GAMMAMARKETS_*`` validation runs before anything else: a
    failure raises here, the host marks the extension inactive, and its
    routes 404 — merchant services never activate on bad configuration.
    Worker registrations land in plans 02-02/02-03.
    """
    global started_at
    from loguru import logger

    from .db import topology_supported
    from .security import audit_capture_warnings
    from .settings import ext_settings  # raises on invalid configuration

    ext_settings()
    ok, reason = topology_supported()
    if not ok:
        raise RuntimeError(f"gammamarkets unsupported topology: {reason}")
    # OQ3: host audit capture has no redaction hook — warn loudly at
    # startup (admin banner repeats it via GET /merchants/current).
    for warning in audit_capture_warnings():
        logger.warning(warning)
    started_at = int(time.time())


def gammamarkets_stop() -> None:
    """Cancel exactly the handles this extension owns (spec section 10)."""
    for task in _owned_tasks:
        task.cancel()
    _owned_tasks.clear()


from .views import gammamarkets_generic_router  # noqa: E402
from .views_api import gammamarkets_api_router  # noqa: E402

gammamarkets_ext.include_router(gammamarkets_generic_router)
gammamarkets_ext.include_router(gammamarkets_api_router)
