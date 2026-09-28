"""§16 metrics hooks — structured counters/gauges for admin surfaces.

In-process aggregation only (no secrets/PII in emitted fields); the admin
health surfaces read these, and log lines carry the same fields.
"""

from __future__ import annotations

import time

_counters: dict[str, int] = {}


def incr(name: str, amount: int = 1) -> None:
    _counters[name] = _counters.get(name, 0) + amount


def get(name: str) -> int:
    return _counters.get(name, 0)


def snapshot() -> dict[str, int]:
    return dict(_counters)


async def outbox_depth() -> dict:
    """Outbox depth + oldest-pending age — the §16 publication gauges."""
    from ..db import db, table

    now = int(time.time())
    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT state, COUNT(*) AS n FROM {table('outbox_events')} "
            "GROUP BY state"
        )
        oldest = await conn.fetchone(
            f"SELECT MIN(created_at) AS oldest FROM {table('outbox_events')} "
            "WHERE state = 'pending'"
        )
    counts = {r["state"]: r["n"] for r in rows}
    oldest_at = oldest["oldest"] if oldest else None
    return {
        "by_state": counts,
        "pending": counts.get("pending", 0),
        "oldest_pending_age_s": (now - oldest_at) if oldest_at else 0,
        "published_total": _counters.get("publication.published", 0),
        "failed_total": counts.get("failed", 0),
    }


async def order_health() -> dict:
    """§16 order gauges — non-terminal orders older than the sanity bound,
    held reservations, open payment projections."""
    from ..db import db, table

    now = int(time.time())
    async with db.connect() as conn:
        stuck = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('orders')} "
            "WHERE state NOT IN ('completed', 'rejected', 'cancelled',"
            " 'expired') AND created_at < :bound",
            {"bound": now - 86400},
        )
        open_orders = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('orders')} "
            "WHERE state NOT IN ('completed', 'rejected', 'cancelled',"
            " 'expired')",
        )
        held = await conn.fetchone(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(quantity), 0) AS qty"
            f" FROM {table('inventory_reservations')} WHERE state = 'held'",
        )
        exceptions = await conn.fetchone(
            f"SELECT COUNT(*) AS n FROM {table('orders')}"
            " WHERE payment_exception",
        )
    return {
        "open_orders": open_orders["n"],
        "stuck_orders": stuck["n"],
        "held_reservations": held["n"],
        "held_units": held["qty"],
        "payment_exceptions": exceptions["n"],
        "settled_total": _counters.get("settlement.confirmed", 0),
        "exception_total": _counters.get("settlement.exception", 0),
    }


async def email_depth() -> dict:
    """§16 email gauges — queue depth by state + send outcomes."""
    from ..db import db, table

    async with db.connect() as conn:
        rows = await conn.fetchall(
            f"SELECT state, COUNT(*) AS n FROM {table('email_queue')}"
            " GROUP BY state"
        )
    counts = {r["state"]: r["n"] for r in rows}
    return {
        "by_state": counts,
        "pending": counts.get("pending", 0),
        "failed": counts.get("failed", 0),
        "sent_total": _counters.get("email.sent", 0),
        "suppressed_total": _counters.get("email.suppressed", 0),
    }
