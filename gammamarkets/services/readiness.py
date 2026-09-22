"""Readiness gate — spec section 8.7/10 structure, created in 02-02.

Public catalog reads may serve once the extension is active; checkout is
gated on the settlement/reconciliation path that lands in 02-03. Until
then every checkout attempt must fail closed with a structured 503 — a
merchant catalog being readable is NOT payment readiness.
"""

from __future__ import annotations

from ..security import ProblemError


def readiness() -> dict:
    """Surface-level readiness flags for admin/public health checks."""
    return {
        "catalog_reads": True,
        "checkout": False,  # settlement saga lands in 02-03
        "reason": "checkout gated until order settlement is active",
    }


def assert_checkout_ready() -> None:
    """Fail closed — called by checkout routes until 02-03 enables them."""
    raise ProblemError(
        503, "checkout-unavailable", "Checkout unavailable",
        "checkout is not yet enabled for this deployment",
    )
