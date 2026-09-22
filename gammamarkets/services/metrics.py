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
