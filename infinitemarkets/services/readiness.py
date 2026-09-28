"""Readiness gate — spec section 8.7/10.

Public catalog reads may serve once the extension is active. Checkout is
gated on settlement readiness: the startup reconciliation pass (§8.7)
must complete first — an order accepted before the recovery scan could
miss a checkpointed crash. ``mark_reconciled`` flips the gate once, from
the reconciliation worker's first completed pass.
"""

from __future__ import annotations

import time

from ..security import ProblemError

_reconciled = False
_database_error: str | None = None


async def _database_timezone() -> str | None:
    from lnbits.core.db import db
    from lnbits.db import POSTGRES

    if db.type != POSTGRES:
        return None
    async with db.connect() as conn:
        row = await conn.fetchone("SELECT current_setting('TimeZone') AS timezone")
    return row["timezone"]


def _process_uses_utc() -> bool:
    return time.timezone == 0 and not (time.daylight and time.altzone != 0)


async def assert_database_compatible() -> None:
    global _database_error
    timezone = await _database_timezone()
    _database_error = None
    if timezone is not None and (
        timezone.upper() not in {"UTC", "ETC/UTC", "GMT", "ETC/GMT"}
        or not _process_uses_utc()
    ):
        _database_error = (
            "PostgreSQL requires UTC database and process timezones "
            "on this LNbits host"
        )
        raise ProblemError(503, "checkout-unavailable", "Checkout unavailable", _database_error)


def mark_reconciled() -> None:
    """Called by the reconciliation worker after its first full pass."""
    global _reconciled
    _reconciled = True


def readiness() -> dict:
    """Surface-level readiness flags for admin/public health checks."""
    return {
        "catalog_reads": True,
        "checkout": _reconciled and _database_error is None,
        "reason": _database_error or (
            "settlement reconciliation active"
            if _reconciled
            else "checkout gated until startup reconciliation completes"
        ),
    }


def assert_checkout_ready() -> None:
    """Fail closed until the startup reconciliation pass completes."""
    if not _reconciled or _database_error is not None:
        raise ProblemError(
            503, "checkout-unavailable", "Checkout unavailable",
            "checkout is not yet ready — retry shortly",
        )
