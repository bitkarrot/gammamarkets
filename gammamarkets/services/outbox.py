"""Transactional outbox enqueue — spec section 8.6.

Every publishable domain mutation inserts an ``outbox_events`` row in
``pending`` INSIDE the same domain transaction. Two rules are enforced
here:

- **Supersession** (§8.6 step 2): older pending intents for the same
  aggregate are marked ``superseded`` — the publisher always rebuilds from
  current state, so a stale intent must never publish outdated content.
- **Dependency edges** (§8.6 ordering): ``outbox_dependencies`` rows wire
  ``30406 → 30405 → 30402`` and "republish survivors before the kind-5
  tombstone" ordering. A dependency edge points at the dep aggregate's
  latest live intent; the worker only claims rows whose deps are
  ``published``.
"""

from __future__ import annotations

import time
import uuid

from ..db import DomainTransaction


def _now() -> int:
    return int(time.time())


async def enqueue_intent(
    tx: DomainTransaction,
    merchant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_kind: int,
    *,
    revision: int = 0,
    event_address: str | None = None,
    depends_on: list[tuple[str, str]] | None = None,
) -> str:
    """Insert a pending intent; returns the new outbox_event id.

    ``depends_on`` is a list of ``(aggregate_type, aggregate_id)`` — each is
    bound to that aggregate's newest live intent (pending/claimed/
    partially_published), so the dependency always tracks the current
    content rather than a superseded row.
    """
    # Supersede older pending intents for this aggregate.
    await tx.execute(
        f"UPDATE {tx.table('outbox_events')} SET state = 'superseded',"
        " updated_at = :t WHERE aggregate_type = :at"
        " AND aggregate_id = :ai AND aggregate_revision < :r"
        " AND state IN ('pending', 'claimed', 'partially_published')",
        {
            "t": _now(),
            "at": aggregate_type,
            "ai": aggregate_id,
            "r": revision,
        },
    )
    # Idempotency: an identical live intent (same aggregate+revision+kind)
    # already covers this enqueue — return it instead of duplicating.
    existing = await tx.fetch_one(
        f"SELECT id FROM {tx.table('outbox_events')} "
        "WHERE aggregate_type = :at AND aggregate_id = :ai"
        " AND aggregate_revision = :r AND event_kind = :k"
        " AND state IN ('pending', 'claimed', 'partially_published')",
        {"at": aggregate_type, "ai": aggregate_id, "r": revision, "k": event_kind},
    )
    if existing:
        return existing["id"]

    intent_id = uuid.uuid4().hex
    await tx.execute(
        f"INSERT INTO {tx.table('outbox_events')} "
        "(id, merchant_id, aggregate_type, aggregate_id, aggregate_revision,"
        " event_kind, event_address, state, attempts, next_attempt_at,"
        " claim_token, created_at, updated_at) "
        "VALUES (:i, :m, :at, :ai, :r, :k, :ea, 'pending', 0, :t, 0, :t, :t)",
        {
            "i": intent_id,
            "m": merchant_id,
            "at": aggregate_type,
            "ai": aggregate_id,
            "r": revision,
            "k": event_kind,
            "ea": event_address,
            "t": _now(),
        },
    )

    for dep_type, dep_id in depends_on or []:
        dep = await tx.fetch_one(
            f"SELECT id FROM {tx.table('outbox_events')} "
            "WHERE aggregate_type = :t AND aggregate_id = :i"
            " AND state IN ('pending', 'claimed', 'partially_published')"
            " ORDER BY aggregate_revision DESC, created_at DESC LIMIT 1",
            {"t": dep_type, "i": dep_id},
        )
        if dep and dep["id"] != intent_id:
            edge = await tx.fetch_one(
                f"SELECT outbox_event_id FROM {tx.table('outbox_dependencies')} "
                "WHERE outbox_event_id = :e"
                " AND depends_on_outbox_event_id = :d",
                {"e": intent_id, "d": dep["id"]},
            )
            if not edge:
                await tx.execute(
                    f"INSERT INTO {tx.table('outbox_dependencies')} "
                    "(outbox_event_id, depends_on_outbox_event_id) "
                    "VALUES (:e, :d)",
                    {"e": intent_id, "d": dep["id"]},
                )
    return intent_id
