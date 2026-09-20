"""Executable inbox/outbox queue models per section 8.5 (checkpoints),
section 8.6 (claim algorithm + outcome policy), and section 8.7 (recovery),
plus the section 9.2 session-time relay-cursor model.

Outbox (``OutboxModel``):

- claim: rows in pending|partially_published with ``next_attempt_at`` due and
  attempts under the bound, only when their ``outbox_dependencies`` are
  published, setting worker id / ``claimed_until`` / incremented
  ``claim_token`` / state=claimed (dialect-specific claim SQL from Task 1);
- outcome policy: zero positive OKs returns the row to pending with backoff
  ``min(2^attempts * 5s, 30min) + jitter``; an incomplete nonzero result
  returns it to partially_published retrying ONLY missing targets; accepted
  copy/relay targets recorded in ``relay_publications`` are NEVER resent;
  NIP-17 rows publish only after at least one recipient-copy AND one
  sender-copy positive OK; exhausted attempts enter failed;
- ``order_msg`` rows keep a stable canonical rumor id across retries while
  outer event ids change (fresh per attempt, persisted in the payload
  descriptor and in ``relay_publications``);
- stale claims requeue only via claim-token CAS reconstruction from durable
  ``relay_publications`` (section 8.7).

Inbox (``InboxModel``): admission persists before processing;
``processed_state`` checkpoints received -> validated -> processed with a
COMMITTED validated checkpoint before domain dispatch; quarantined rows are
retained with a bounded reason and no plaintext; the merchant's own sender
copy is recovered as a sender copy without dispatching a domain command
(section 8.5 step 7); admitted rows left received|validated are reprocessed
on restart (section 8.7).

Relay cursors (``CursorModel``): advance only after EOSE with durably
admitted events — session-time cursors, never event-time; a crash before EOSE
leaves the prior cursor intact.

Backoff jitter is deterministic in the model (0 by default; the spec's
0-5s jitter is a deployment property) so restart assertions stay exact.
"""

from __future__ import annotations

import json
import uuid

from harness import state as state_module
from harness import tx


def backoff_delay(attempts: int, *, base_s: int = 5, max_s: int = 1800) -> int:
    """``min(2^attempts * 5s, 30min)`` (section 8.6; jitter is a deployment
    property and stays deterministic in the model)."""
    return min(2 ** attempts * base_s, max_s)


class OutboxModel:
    """Section 8.6 publish algorithm + section 8.7 outbox recovery."""

    MAX_ATTEMPTS = 20
    CLAIM_STATES = ("pending", "partially_published")

    def __init__(self, qual_db, *, jitter_fn=None) -> None:
        self.qual_db = qual_db
        self._jitter_fn = jitter_fn or (lambda row_id, attempts: 0)
        #: Fresh outer event ids generated per publish attempt (evidence).
        self.outer_event_ids: dict[str, list[str]] = {}

    # --- enqueue -------------------------------------------------------------

    async def enqueue(
        self,
        *,
        intent_id: str | None,
        merchant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_revision: int = 0,
        event_kind: int = 30402,
        payload: dict | None = None,
        targets: list[dict] | None = None,
        depends_on: list[str] | None = None,
        now: int | None = None,
    ) -> dict:
        """Insert one pending outbox intent (deterministic id => idempotent)."""
        now = tx.db_now() if now is None else now
        intent_id = intent_id or f"obx-{uuid.uuid4().hex[:16]}"
        payload = dict(payload or {})
        if targets is not None:
            payload["targets"] = targets
        # ON CONFLICT DO NOTHING: atomic idempotent insert (deterministic
        # ids) without poisoning the transaction on either dialect.
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                rc = await t.execute(
                    f"INSERT INTO {self.qual_db.table('outbox_events')}"
                    " (id, merchant_id, aggregate_type, aggregate_id,"
                    "  aggregate_revision, event_kind, state, payload_json,"
                    "  next_attempt_at, created_at, updated_at)"
                    " VALUES (:id, :merchant_id, :aggregate_type,"
                    "  :aggregate_id, :aggregate_revision, :event_kind,"
                    "  'pending', :payload_json, 0, :now, :now)"
                    " ON CONFLICT DO NOTHING",
                    {
                        "id": intent_id,
                        "merchant_id": merchant_id,
                        "aggregate_type": aggregate_type,
                        "aggregate_id": aggregate_id,
                        "aggregate_revision": aggregate_revision,
                        "event_kind": event_kind,
                        "payload_json": json.dumps(payload),
                        "now": now,
                    },
                )
                if rc == 1:
                    for dep in depends_on or []:
                        await t.execute(
                            f"INSERT INTO {self.qual_db.table('outbox_dependencies')}"
                            " (outbox_event_id, depends_on_outbox_event_id)"
                            " VALUES (:id, :dep) ON CONFLICT DO NOTHING",
                            {"id": intent_id, "dep": dep},
                        )
        return await self._row(intent_id)

    async def _row(self, intent_id: str) -> dict:
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('outbox_events')}"
            " WHERE id = :id",
            {"id": intent_id},
        )
        if not rows:
            raise KeyError(f"outbox intent {intent_id!r} does not exist")
        return rows[0]

    # --- claim ----------------------------------------------------------------

    async def claim(
        self,
        *,
        worker: str = "outbox-worker-1",
        now: int | None = None,
        limit: int = 32,
        lease_seconds: int = 60,
        max_attempts: int | None = None,
    ) -> list[dict]:
        """Section 8.6 step 1 claim (published-dependencies only)."""
        now = tx.db_now() if now is None else now
        deps = self.qual_db.table("outbox_dependencies")
        events = self.qual_db.table("outbox_events")
        extra_where = (
            "NOT EXISTS ("
            f"  SELECT 1 FROM {deps} d JOIN {events} dep"
            "    ON dep.id = d.depends_on_outbox_event_id"
            "  WHERE d.outbox_event_id = outbox_events.id"
            "    AND dep.state != 'published')"
        )
        if self.qual_db.dialect == "postgres":
            # Correlate by the bare table name (the outer UPDATE target).
            extra_where = extra_where.replace(
                "outbox_events.id", f"{events}.id"
            )
        return await tx.claim_due_rows(
            self.qual_db,
            events,
            states=list(self.CLAIM_STATES),
            now=now,
            max_attempts=max_attempts or self.MAX_ATTEMPTS,
            limit=limit,
            worker=worker,
            lease_seconds=lease_seconds,
            extra_where=extra_where,
        )

    # --- publish + outcome policy ---------------------------------------------

    async def accepted_targets(self, intent_id: str) -> set[tuple[str, str]]:
        """Durable positive evidence: (delivery_copy, relay_url) accepted."""
        rows = await self.qual_db.fetch_all(
            f"SELECT delivery_copy, relay_url FROM"
            f" {self.qual_db.table('relay_publications')}"
            " WHERE outbox_event_id = :id AND result = 'accepted'",
            {"id": intent_id},
        )
        return {(row["delivery_copy"], row["relay_url"]) for row in rows}

    def declared_targets(self, row: dict) -> list[dict]:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return list(payload.get("targets", []))

    def missing_targets(self, row: dict, accepted: set[tuple[str, str]]) -> list[dict]:
        """Targets not yet durably accepted — accepted targets are never resent."""
        return [
            target
            for target in self.declared_targets(row)
            if (target.get("delivery_copy", "public"), target["relay_url"])
            not in accepted
        ]

    async def publish_attempt(
        self, row: dict, *, now: int | None = None
    ) -> list[dict]:
        """One publish attempt against the MISSING targets only.

        Generates fresh outer event ids per target (section 8.6 step 3:
        retries reuse the same rumor id but create fresh seals/wrappers/
        outer event ids). The stable canonical rumor id for ``order_msg``
        rows lives in the payload descriptor and never changes.
        """
        now = tx.db_now() if now is None else now
        accepted = await self.accepted_targets(row["id"])
        missing = self.missing_targets(row, accepted)
        attempt_ids = []
        for index, target in enumerate(missing):
            # Fresh outer event id per attempt; the rumor id (payload) is
            # stable across retries for order_msg rows.
            outer_id = f"outer-{row['id']}-{row['attempts'] + 1}-{index}-{uuid.uuid4().hex[:8]}"
            attempt_ids.append(outer_id)
        self.outer_event_ids[row["id"]] = attempt_ids
        # Persist the fresh outer ids into the payload descriptor (a leased
        # write: claim-token CAS + live lease).
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        payload["current_outer_event_ids"] = attempt_ids
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                await tx.leased_write(
                    t,
                    self.qual_db.table("outbox_events"),
                    "payload_json = :payload_json, state = 'publishing',"
                    " updated_at = :now",
                    {
                        "id": row["id"],
                        "claim_token": row["claim_token"],
                        "now": now,
                        "payload_json": json.dumps(payload),
                    },
                )
        return [
            {**target, "event_id": outer_id}
            for target, outer_id in zip(missing, attempt_ids, strict=True)
        ]

    def _quorum_met(self, row: dict, accepted: set[tuple[str, str]]) -> bool:
        if row["aggregate_type"] == "order_msg":
            # NIP-17: at least one recipient-copy AND one sender-copy
            # positive OK (section 8.6 step 8).
            copies = {copy for copy, _relay in accepted}
            return "recipient" in copies and "sender" in copies
        return bool(accepted)

    async def record_publications(
        self, row: dict, outcomes: list[dict], *, now: int | None = None
    ) -> None:
        """Record durable per-target publication evidence (section 8.6 step 6).

        ``outcomes``: one entry per attempted target —
        ``{delivery_copy, relay_url, event_id, result, message?}`` with
        result in accepted|rejected|timeout. One ``relay_publications`` row
        is inserted per copy/relay/attempt; positive evidence is durable and
        append-only (UNIQUE per attempt), so a crash between publishing and
        the outcome-policy write still leaves the accepted targets
        reconstructable.
        """
        now = tx.db_now() if now is None else now
        attempt_no = row["attempts"] + 1
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                for outcome in outcomes:
                    await t.execute(
                        f"INSERT INTO {self.qual_db.table('relay_publications')}"
                        " (id, outbox_event_id, delivery_copy, relay_url,"
                        "  event_id, attempt_no, result, message, attempted_at)"
                        " VALUES (:id, :outbox_event_id, :delivery_copy,"
                        "  :relay_url, :event_id, :attempt_no, :result,"
                        "  :message, :now)",
                        {
                            "id": f"rp-{uuid.uuid4().hex[:16]}",
                            "outbox_event_id": row["id"],
                            "delivery_copy": outcome.get(
                                "delivery_copy", "public"
                            ),
                            "relay_url": outcome["relay_url"],
                            "event_id": outcome.get("event_id", ""),
                            "attempt_no": attempt_no,
                            "result": outcome["result"],
                            "message": outcome.get("message"),
                            "now": now,
                        },
                    )

    async def apply_outcome(
        self, row: dict, *, now: int | None = None
    ) -> dict:
        """Apply the section 8.6 outcome policy from DURABLE evidence.

        Quorum is evaluated over the cumulative accepted
        ``relay_publications`` (accepted targets are never resent):

        - quorum met -> published (public: >= 1 positive OK; order_msg:
          >= 1 recipient-copy AND >= 1 sender-copy positive OK);
        - some positive evidence but incomplete quorum -> partially_published
          with backoff (retries only missing targets);
        - zero positive OKs -> pending with backoff min(2^attempts*5s, 30min);
        - exhausted attempts (MAX_ATTEMPTS) -> failed.
        """
        now = tx.db_now() if now is None else now
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                accepted = {
                    (r["delivery_copy"], r["relay_url"])
                    for r in await t.fetch_all(
                        f"SELECT delivery_copy, relay_url FROM"
                        f" {self.qual_db.table('relay_publications')}"
                        " WHERE outbox_event_id = :id AND result = 'accepted'",
                        {"id": row["id"]},
                    )
                }
                new_attempts = row["attempts"] + 1
                if self._quorum_met(row, accepted):
                    new_state = "published"
                elif accepted:
                    # At least one positive OK but an incomplete quorum:
                    # retry only missing targets.
                    new_state = "partially_published"
                else:
                    # Zero positive OKs: back to pending with backoff.
                    new_state = "pending"
                if new_state != "published" and new_attempts >= self.MAX_ATTEMPTS:
                    new_state = "failed"
                delay = (
                    backoff_delay(new_attempts)
                    + self._jitter_fn(row["id"], new_attempts)
                    if new_state != "published"
                    else 0
                )
                await tx.leased_write(
                    t,
                    self.qual_db.table("outbox_events"),
                    "state = :new_state, attempts = :new_attempts,"
                    " next_attempt_at = :next_attempt_at, updated_at = :now,"
                    " claimed_by = NULL, claimed_at = NULL, claimed_until = NULL",
                    {
                        "id": row["id"],
                        "claim_token": row["claim_token"],
                        "now": now,
                        "new_state": new_state,
                        "new_attempts": new_attempts,
                        "next_attempt_at": now + delay,
                    },
                )
        return {"id": row["id"], "state": new_state, "attempts": new_attempts}

    async def record_outcomes(
        self, row: dict, outcomes: list[dict], *, now: int | None = None
    ) -> dict:
        """Record publication evidence, then apply the outcome policy."""
        now = tx.db_now() if now is None else now
        await self.record_publications(row, outcomes, now=now)
        return await self.apply_outcome(row, now=now)

    # --- section 8.7 recovery ---------------------------------------------------

    async def requeue_stale(self, *, now: int | None = None) -> list[dict]:
        """Reclaim stale outbox rows only with a claim-token CAS.

        Covers rows left ``claimed`` OR ``publishing`` with an expired
        lease (a crash mid-publish leaves ``publishing``). Reconstruction
        from durable positive ``relay_publications``: a row with no
        accepted evidence returns to pending; a row with accepted evidence
        returns to partially_published (retry only missing targets). The
        CAS carries the OLD claim token and increments it, so a stale
        worker's later leased write fails (section 7.4).
        """
        now = tx.db_now() if now is None else now
        events = self.qual_db.table("outbox_events")
        stale = await self.qual_db.fetch_all(
            f"SELECT * FROM {events} WHERE state IN ('claimed', 'publishing')"
            " AND claimed_until <= :now",
            {"now": now},
        )
        requeued = []
        for row in stale:
            accepted = await self.accepted_targets(row["id"])
            new_state = "partially_published" if accepted else "pending"
            async with self.qual_db.connect() as conn:
                async with self.qual_db.transaction(conn) as t:
                    rc = await t.execute(
                        f"UPDATE {events} SET state = :new_state,"
                        " claimed_by = NULL, claimed_at = NULL,"
                        " claimed_until = NULL, claim_token = claim_token + 1,"
                        " next_attempt_at = :now, updated_at = :now"
                        " WHERE id = :id AND claim_token = :claim_token"
                        " AND claimed_until <= :now",
                        {
                            "new_state": new_state,
                            "now": now,
                            "id": row["id"],
                            "claim_token": row["claim_token"],
                        },
                    )
                    if rc != 1:  # pragma: no cover - another actor requeued first
                        raise tx.StaleClaim(
                            f"stale-claim requeue CAS lost for {row['id']!r}"
                        )
            requeued.append({"id": row["id"], "state": new_state})
        return requeued

    async def supersede_obsolete(self, *, now: int | None = None) -> list[str]:
        """Section 7.4/8.6 step 2: supersede public rows with a newer revision.

        ``order_msg`` rows are NEVER superseded.
        """
        now = tx.db_now() if now is None else now
        events = self.qual_db.table("outbox_events")
        superseded = []
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {events} WHERE"
            f" {self._in_list('state', state_module.OUTBOX_SUPERSEDABLE_STATES)}",
        )
        for row in rows:
            if row["aggregate_type"] in state_module.OUTBOX_NON_SUPERSEDABLE_AGGREGATES:
                continue
            newer = await self.qual_db.fetch_all(
                f"SELECT id FROM {events} WHERE aggregate_type = :aggregate_type"
                " AND aggregate_id = :aggregate_id AND event_kind = :event_kind"
                " AND aggregate_revision > :aggregate_revision AND id != :id",
                {
                    "aggregate_type": row["aggregate_type"],
                    "aggregate_id": row["aggregate_id"],
                    "event_kind": row["event_kind"],
                    "aggregate_revision": row["aggregate_revision"],
                    "id": row["id"],
                },
            )
            if newer:
                async with self.qual_db.connect() as conn:
                    async with self.qual_db.transaction(conn) as t:
                        await t.execute(
                            f"UPDATE {events} SET state = 'superseded',"
                            " updated_at = :now WHERE id = :id",
                            {"now": now, "id": row["id"]},
                        )
                superseded.append(row["id"])
        return superseded

    @staticmethod
    def _in_list(column: str, values: tuple[str, ...]) -> str:
        quoted = ", ".join(f"'{value}'" for value in values)
        return f"({column} IN ({quoted}))"


class InboxModel:
    """Section 8.5 ingest checkpoints + section 8.7 inbox recovery."""

    def __init__(self, qual_db) -> None:
        self.qual_db = qual_db
        #: Evidence: which admitted rows were dispatched to the domain.
        self.dispatched: list[str] = []

    async def admit(
        self,
        *,
        outer_event_id: str,
        rumor_id: str | None,
        merchant_id: str,
        kind: int = 1059,
        author_hash: str,
        source_relay_url: str = "wss://relay.example",
        raw_json: str | None = None,
        now: int | None = None,
    ) -> dict:
        """Durable handoff: persist BEFORE processing (section 8.5).

        A duplicate ``outer_event_id`` is a successful no-op (UNIQUE insert).
        """
        now = tx.db_now() if now is None else now
        row_id = f"ibx-{uuid.uuid4().hex[:16]}"
        try:
            async with self.qual_db.connect() as conn:
                async with self.qual_db.transaction(conn) as t:
                    await t.execute(
                        f"INSERT INTO {self.qual_db.table('inbox_events')}"
                        " (id, outer_event_id, rumor_id, merchant_id,"
                        "  source_relay_url, received_at, kind, author_hash,"
                        "  processed_state, raw_json)"
                        " VALUES (:id, :outer_event_id, :rumor_id, :merchant_id,"
                        "  :source_relay_url, :now, :kind, :author_hash,"
                        "  'received', :raw_json)",
                        {
                            "id": row_id,
                            "outer_event_id": outer_event_id,
                            "rumor_id": rumor_id,
                            "merchant_id": merchant_id,
                            "source_relay_url": source_relay_url,
                            "now": now,
                            "kind": kind,
                            "author_hash": author_hash,
                            "raw_json": raw_json,
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            if "IntegrityError" not in type(exc).__name__:
                raise
            # A UNIQUE violation: duplicate outer_event_id (or rumor_id where
            # present) — a successful no-op (section 8.5). PostgreSQL
            # aborts the failed transaction, so look up the existing row in
            # a fresh one.
            existing = await self.qual_db.fetch_all(
                f"SELECT * FROM {self.qual_db.table('inbox_events')}"
                " WHERE outer_event_id = :outer_event_id",
                {"outer_event_id": outer_event_id},
            )
            if not existing and rumor_id:
                existing = await self.qual_db.fetch_all(
                    f"SELECT * FROM {self.qual_db.table('inbox_events')}"
                    " WHERE rumor_id = :rumor_id",
                    {"rumor_id": rumor_id},
                )
            if not existing:  # pragma: no cover - unexpected constraint
                raise
            return {**existing[0], "duplicate": True}
        return {**await self.row(row_id), "duplicate": False}

    async def row(self, row_id: str) -> dict:
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('inbox_events')} WHERE id = :id",
            {"id": row_id},
        )
        if not rows:
            raise KeyError(f"inbox row {row_id!r} does not exist")
        return rows[0]

    async def _transition(
        self, row_id: str, *, to_state: str, now: int, reason: str | None = None
    ) -> None:
        """processed_state checkpoint CAS (received->validated->processed ...)."""
        legal = state_module.INBOX_TRANSITIONS
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                rows = await t.fetch_all(
                    f"SELECT processed_state FROM {self.qual_db.table('inbox_events')}"
                    " WHERE id = :id",
                    {"id": row_id},
                )
                current = rows[0]["processed_state"]
                if to_state not in legal.get(current, frozenset()):
                    raise state_module.IllegalTransition(
                        f"illegal inbox transition {current!r} -> {to_state!r}"
                        " (section 7.5)"
                    )
                await t.execute(
                    f"UPDATE {self.qual_db.table('inbox_events')}"
                    " SET processed_state = :to_state, processed_at = :now,"
                    " reject_reason = :reason"
                    " WHERE id = :id AND processed_state = :from_state",
                    {
                        "to_state": to_state,
                        "now": now,
                        "id": row_id,
                        "from_state": current,
                        # Bounded reason, no plaintext (section 8.5 step 10).
                        "reason": reason[:128] if reason else None,
                    },
                )

    async def validate(self, row_id: str, *, now: int | None = None) -> None:
        """The committed validated checkpoint BEFORE domain dispatch."""
        now = tx.db_now() if now is None else now
        await self._transition(row_id, to_state="validated", now=now)

    async def dispatch(self, row_id: str, *, now: int | None = None) -> dict:
        """Domain dispatch for a validated row.

        Section 8.5 step 7: if the rumor id matches one of OUR outbound
        order_msg intents (the merchant's own sender copy), recover it as a
        sender copy WITHOUT dispatching a domain command.
        """
        now = tx.db_now() if now is None else now
        row = await self.row(row_id)
        if row["processed_state"] != "validated":
            raise state_module.IllegalTransition(
                f"dispatch requires a validated row, got {row['processed_state']!r}"
            )
        sender_copy = await self._is_outbound_rumor(row["rumor_id"])
        await self._transition(row_id, to_state="processed", now=now)
        if sender_copy:
            return {"row_id": row_id, "action": "sender-copy-recovered"}
        self.dispatched.append(row_id)
        return {"row_id": row_id, "action": "dispatched"}

    async def _is_outbound_rumor(self, rumor_id: str | None) -> bool:
        if not rumor_id:
            return False
        # The outbound order_msg intents carry the canonical rumor id in
        # their payload descriptor (portable LIKE match on both dialects).
        rows = await self.qual_db.fetch_all(
            f"SELECT id FROM {self.qual_db.table('outbox_events')}"
            " WHERE aggregate_type = 'order_msg' AND payload_json LIKE :pattern",
            {"pattern": f'%"rumor_id": "{rumor_id}"%'},
        )
        return bool(rows)

    async def quarantine(
        self, row_id: str, *, reason: str, now: int | None = None
    ) -> None:
        """Retained for inspection with a bounded reason, no plaintext."""
        now = tx.db_now() if now is None else now
        await self._transition(row_id, to_state="quarantined", now=now, reason=reason)

    async def resume(self, *, now: int | None = None) -> dict:
        """Section 8.7: reprocess admitted rows left received|validated."""
        now = tx.db_now() if now is None else now
        report = {"validated": [], "dispatched": [], "recovered": []}
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('inbox_events')}"
            " WHERE processed_state IN ('received', 'validated')"
        )
        for row in rows:
            if row["processed_state"] == "received":
                await self.validate(row["id"], now=now)
                report["validated"].append(row["id"])
            result = await self.dispatch(row["id"], now=now)
            if result["action"] == "sender-copy-recovered":
                report["recovered"].append(row["id"])
            else:
                report["dispatched"].append(row["id"])
        return report


class CursorModel:
    """Section 9.2 relay cursors: session-time, advance only after EOSE."""

    def __init__(self, qual_db, *, merchant_id: str = "merchant-1") -> None:
        self.qual_db = qual_db
        self.merchant_id = merchant_id
        # In-memory session registry: a crash (discarding the model) loses the
        # session but never the persisted cursor — the prior cursor stays.
        self._sessions: dict[str, dict] = {}

    async def start_session(
        self, *, relay_url: str, protocol: str = "nip17", now: int | None = None
    ) -> str:
        """Begin a subscription session. Persists NOTHING yet."""
        now = tx.db_now() if now is None else now
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        self._sessions[session_id] = {
            "relay_url": relay_url,
            "protocol": protocol,
            "started_at": now,
        }
        return session_id

    async def complete_session(
        self, session_id: str, *, now: int | None = None
    ) -> bool:
        """Persist the cursor AFTER EOSE with all pre-EOSE events admitted.

        The cursor records the session START time (never event time) and
        never regresses.
        """
        if session_id not in self._sessions:
            raise KeyError(f"unknown session {session_id!r}")
        now = tx.db_now() if now is None else now
        session = self._sessions[session_id]
        cursor_id = f"cur-{uuid.uuid4().hex[:12]}"
        async with self.qual_db.connect() as conn:
            async with self.qual_db.transaction(conn) as t:
                existing = await t.fetch_all(
                    f"SELECT * FROM {self.qual_db.table('relay_cursors')}"
                    " WHERE merchant_id = :merchant_id AND relay_url = :relay_url"
                    " AND protocol = :protocol",
                    {
                        "merchant_id": self.merchant_id,
                        "relay_url": session["relay_url"],
                        "protocol": session["protocol"],
                    },
                )
                if not existing:
                    await t.execute(
                        f"INSERT INTO {self.qual_db.table('relay_cursors')}"
                        " (id, merchant_id, relay_url, protocol,"
                        "  last_completed_session_start, eose_session_id,"
                        "  eose_at, updated_at)"
                        " VALUES (:id, :merchant_id, :relay_url, :protocol,"
                        "  :start, :session_id, :now, :now)",
                        {
                            "id": cursor_id,
                            "merchant_id": self.merchant_id,
                            "relay_url": session["relay_url"],
                            "protocol": session["protocol"],
                            "start": session["started_at"],
                            "session_id": session_id,
                            "now": now,
                        },
                    )
                    return True
                current = existing[0]
                # Never regress: only advance to a LATER session start.
                if (
                    current["last_completed_session_start"] is None
                    or current["last_completed_session_start"]
                    < session["started_at"]
                ):
                    await t.execute(
                        f"UPDATE {self.qual_db.table('relay_cursors')}"
                        " SET last_completed_session_start = :start,"
                        " eose_session_id = :session_id, eose_at = :now,"
                        " updated_at = :now WHERE id = :id",
                        {
                            "start": session["started_at"],
                            "session_id": session_id,
                            "now": now,
                            "id": current["id"],
                        },
                    )
                    return True
                return False

    async def cursor(self, *, relay_url: str, protocol: str = "nip17") -> dict | None:
        rows = await self.qual_db.fetch_all(
            f"SELECT * FROM {self.qual_db.table('relay_cursors')}"
            " WHERE merchant_id = :merchant_id AND relay_url = :relay_url"
            " AND protocol = :protocol",
            {
                "merchant_id": self.merchant_id,
                "relay_url": relay_url,
                "protocol": protocol,
            },
        )
        return rows[0] if rows else None
