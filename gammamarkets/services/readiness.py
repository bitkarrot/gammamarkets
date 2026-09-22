"""Readiness gate — spec section 8.7/10.

Public catalog reads may serve once the extension is active. Checkout is
gated on settlement readiness: the startup reconciliation pass (§8.7)
must complete first — an order accepted before the recovery scan could
miss a checkpointed crash. ``mark_reconciled`` flips the gate once, from
the reconciliation worker's first completed pass.
"""

from __future__ import annotations

from ..security import ProblemError

_reconciled = False


def mark_reconciled() -> None:
    """Called by the reconciliation worker after its first full pass."""
    global _reconciled
    _reconciled = True


def readiness() -> dict:
    """Surface-level readiness flags for admin/public health checks."""
    return {
        "catalog_reads": True,
        "checkout": _reconciled,
        "reason": (
            "settlement reconciliation active"
            if _reconciled
            else "checkout gated until startup reconciliation completes"
        ),
    }


def assert_checkout_ready() -> None:
    """Fail closed until the startup reconciliation pass completes."""
    if not _reconciled:
        raise ProblemError(
            503, "checkout-unavailable", "Checkout unavailable",
            "checkout is not yet ready — retry shortly",
        )
