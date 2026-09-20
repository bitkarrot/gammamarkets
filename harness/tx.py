"""Section 14 transaction adapter for the qualification harness.

One ``Database.connect()`` context per domain transaction; raw parameterized
statements only; explicit commit/rollback. The host's auto-committing
``Connection``/``Database`` helper methods (``execute``/``insert``/``update``)
are NEVER called inside a domain transaction — their use is forbidden by
section 14 and proven by the P0-06 auto-commit-splitting probe.

Dialect paths (both verified against the pinned stack):

- SQLite: ``BEGIN IMMEDIATE`` on the raw aiosqlite connection, raw statements
  with named ``:param`` placeholders (sqlite3 native named-parameter style),
  explicit ``commit()``/``rollback()`` on the raw connection.
- PostgreSQL: ``conn.conn.begin()`` (SQLAlchemy-managed transaction) with
  schema-qualified tables and raw ``text()``-level statements.

All statements use the SAME named-parameter ``:param`` spelling on both
dialects — sqlite3 binds dict parameters natively.

Section 8.6 claim rules (dialect-specific by design, never a supposedly
portable ``UPDATE ... IN (SELECT ...)``):

- PostgreSQL: one ``UPDATE ... WHERE id IN (SELECT ... FOR UPDATE
  SKIP LOCKED) RETURNING *`` statement.
- SQLite: bounded select-then-update inside ``BEGIN IMMEDIATE`` (the single
  SQLite writer makes select-then-update atomic).

Every leased write compares the active ``claim_token``; task-lease writes
compare the monotonically increasing ``fencing_token`` (section 4.16).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from lnbits.db import Connection

from harness import db as db_module


class SagaConflict(Exception):
    """A section 8.2 step-1 saga precondition lost; the transaction rolled back."""


class LeaseHeld(Exception):
    """A live task lease is held by another worker (section 4.16)."""


class StaleFencingToken(Exception):
    """A fenced write carried a fencing token that is no longer current."""


class StaleClaim(Exception):
    """A leased queue write lost its claim-token CAS (section 8.6)."""


def db_now() -> int:
    """The harness clock: UTC unix epoch seconds (schema timestamp style)."""
    return int(time.time())


# --- Section 8.2 step-1 statement builders (schema-qualified via db.table) ---


def claim_stock_sql(table: str) -> str:
    """Conditional stock claim: only when unreserved stock covers the qty."""
    return (
        f"UPDATE {table} SET stock_reserved = stock_reserved + :qty"
        " WHERE id = :product_id AND deleted_at IS NULL"
        " AND (stock_on_hand IS NULL OR stock_on_hand - stock_reserved >= :qty)"
    )


def cas_order_state_sql(table: str) -> str:
    """Compare-and-swap order transition (expected rowcount exactly 1)."""
    return (
        f"UPDATE {table} SET state = :to_state"
        " WHERE id = :order_id AND state = :from_state"
    )


def insert_reservation_sql(table: str) -> str:
    """Insert a held inventory reservation."""
    return (
        f"INSERT INTO {table}"
        " (id, product_id, order_id, quantity, state, expires_at,"
        " created_at, updated_at)"
        " VALUES (:id, :product_id, :order_id, :qty, :state, :expires_at,"
        " :now, :now)"
    )


def insert_payment_projection_sql(table: str) -> str:
    """Insert the local payment projection (section 8.2 step 1)."""
    return (
        f"INSERT INTO {table}"
        " (id, order_id, core_external_id, checking_id_enc, wallet_refs_enc,"
        " wallet_id_hash, source_wallet_id_hash, amount_sat, status, created_at)"
        " VALUES (:id, :order_id, :core_external_id, :checking_id_enc,"
        " :wallet_refs_enc, :wallet_id_hash, :source_wallet_id_hash,"
        " :amount_sat, :status, :now)"
    )


def _in_clause(column: str, values: list) -> tuple[str, dict]:
    """``column IN (:v0, :v1, ...)`` with named params (raw text()-portable)."""
    params = {f"v{i}": value for i, value in enumerate(values)}
    placeholders = ", ".join(f":v{i}" for i in range(len(values)))
    return f"{column} IN ({placeholders})", params


class DomainTransaction:
    """One domain transaction on an open host Connection (section 14)."""

    def __init__(self, conn: Connection, dialect: str) -> None:
        self._conn = conn
        self._dialect = dialect
        self._pg_tx = None
        self._raw = None

    async def __aenter__(self) -> "DomainTransaction":
        if self._dialect == "sqlite":
            self._raw = db_module.raw_sqlite_connection(self._conn)
            await self._raw.execute("BEGIN IMMEDIATE")
        else:
            self._pg_tx = await self._conn.conn.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            await self.commit()
        else:
            await self.rollback()
        return None

    async def commit(self) -> None:
        if self._raw is not None:
            await self._raw.commit()
        elif self._pg_tx is not None:
            await self._pg_tx.commit()

    async def rollback(self) -> None:
        if self._raw is not None:
            await self._raw.rollback()
        elif self._pg_tx is not None:
            await self._pg_tx.rollback()

    async def execute(self, sql: str, params: dict | None = None) -> int:
        """Execute one raw parameterized statement; return the rowcount."""
        if self._raw is not None:
            cursor = await self._raw.execute(sql, params or {})
            return cursor.rowcount
        from sqlalchemy.sql import text

        result = await self._conn.conn.execute(text(sql), params or {})
        return result.rowcount

    async def fetch_all(self, sql: str, params: dict | None = None) -> list[dict]:
        """Read rows inside the transaction."""
        if self._raw is not None:
            cursor = await self._raw.execute(sql, params or {})
            columns = [d[0] for d in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        from sqlalchemy.sql import text

        result = await self._conn.conn.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]


async def fetch_all(
    conn: Connection, dialect: str, sql: str, params: dict | None = None
) -> list[dict]:
    """Read rows OUTSIDE any domain transaction (commit-hygienic for PG)."""
    if dialect == "sqlite":
        raw = db_module.raw_sqlite_connection(conn)
        cursor = await raw.execute(sql, params or {})
        columns = [d[0] for d in cursor.description]
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    from sqlalchemy.sql import text

    result = await conn.conn.execute(text(sql), params or {})
    rows = [dict(row) for row in result.mappings().all()]
    # End the SQLAlchemy autobegin left open by the SELECT so a following
    # begin() stays available (SQLAlchemy 1.4 keeps autobegin open otherwise).
    await conn.conn.commit()
    return rows


async def fetch_one(
    conn: Connection, dialect: str, sql: str, params: dict | None = None
) -> dict | None:
    """Read a single row outside any domain transaction."""
    rows = await fetch_all(conn, dialect, sql, params)
    return rows[0] if rows else None


# --- Section 8.2 step 1: conditional claim, CAS, reservations, projection ---


async def claim_and_reserve_multi(
    qual_db,
    *,
    items: list[dict],
    order_id: str,
    from_state: str = "received",
    to_state: str = "invoice_pending",
    expires_at: int,
    now: int | None = None,
    payment: dict | None = None,
    pause_hook: Callable[[str], Awaitable[None]] | None = None,
) -> None:
    """Section 8.2 step 1 for a whole cart as ONE transaction.

    ``items`` is a list of ``{product_id, qty, reservation_id}`` dicts.
    Products are claimed in **sorted id order** (section 8.2: avoids
    PostgreSQL deadlocks between concurrent multi-item claims). Any lost
    stock guard, CAS, or constraint rolls back the ENTIRE claim set and
    raises ``SagaConflict`` — exactly one concurrent worker can win.

    The order transition goes through ``state.transition_order`` so the
    ``order_events`` audit row is written in the same transaction (section
    7.1). When ``payment`` is given (``{id, core_external_id, checking_id_enc,
    wallet_refs_enc, wallet_id_hash, source_wallet_id_hash, amount_sat}``),
    the local payment projection is inserted with ``status=creating`` in the
    same transaction (section 8.2 step 1).

    ``pause_hook`` is an optional test seam called with each product id
    right after its claim, while the transaction (and its locks) are held —
    the deadlock-avoidance probe uses it to force claim interleaving.
    """
    from harness import state as state_module

    now = db_now() if now is None else now
    async with qual_db.connect() as conn:
        async with qual_db.transaction(conn) as t:
            for item in sorted(items, key=lambda i: i["product_id"]):
                rc = await t.execute(
                    claim_stock_sql(qual_db.table("products")),
                    {"qty": item["qty"], "product_id": item["product_id"]},
                )
                if rc != 1:
                    raise SagaConflict(
                        f"stock claim failed for product {item['product_id']}"
                    )
                if pause_hook is not None:
                    await pause_hook(item["product_id"])
            await state_module.transition_order(
                t,
                qual_db,
                order_id=order_id,
                from_state=from_state,
                to_state=to_state,
                actor="system",
                now=now,
            )
            for item in items:
                await t.execute(
                    insert_reservation_sql(
                        qual_db.table("inventory_reservations")
                    ),
                    {
                        "id": item["reservation_id"],
                        "product_id": item["product_id"],
                        "order_id": order_id,
                        "qty": item["qty"],
                        "state": "held",
                        "expires_at": expires_at,
                        "now": now,
                    },
                )
            if payment is not None:
                await t.execute(
                    insert_payment_projection_sql(qual_db.table("payments")),
                    {**payment, "order_id": order_id, "status": "creating", "now": now},
                )


async def claim_and_reserve(
    qual_db,
    *,
    product_id: str,
    qty: int,
    order_id: str,
    reservation_id: str,
    expires_at: int,
    from_state: str = "received",
    to_state: str = "invoice_pending",
) -> None:
    """Section 8.2 step 1 for a single-item cart (tracer-compatible shape).

    Conditionally claims stock (guard: stock_on_hand - stock_reserved >= qty,
    product not deleted), transitions the order with compare-and-swap and an
    ``order_events`` audit row, and inserts a ``held`` reservation. If ANY
    rowcount != 1 the entire transaction rolls back and ``SagaConflict`` is
    raised — exactly one concurrent worker can win this transition.
    """
    await claim_and_reserve_multi(
        qual_db,
        items=[{"product_id": product_id, "qty": qty, "reservation_id": reservation_id}],
        order_id=order_id,
        from_state=from_state,
        to_state=to_state,
        expires_at=expires_at,
    )


# --- Section 8.6/8.8 claim algorithm (dialect-specific) ---


async def claim_due_rows(
    qual_db,
    table: str,
    *,
    states: list[str],
    now: int,
    max_attempts: int,
    limit: int,
    worker: str,
    lease_seconds: int,
) -> list[dict]:
    """Atomically claim up to ``limit`` due queue rows (section 8.6 step 1).

    Selects rows with ``state IN states``, ``next_attempt_at <= now``, and
    ``attempts < max_attempts``; sets ``state='claimed'``, ``claimed_by``,
    ``claimed_at``, ``claimed_until``, and increments ``claim_token``.
    Returns the claimed rows (post-update values).

    PostgreSQL claims with ``FOR UPDATE SKIP LOCKED`` in one statement;
    SQLite uses a bounded select-then-update inside ``BEGIN IMMEDIATE``.
    """
    state_clause, state_params = _in_clause("state", list(states))
    until = now + lease_seconds
    claimed_params = {
        "worker": worker,
        "now": now,
        "until": until,
        "max_attempts": max_attempts,
        "limit": limit,
    }

    async with qual_db.connect() as conn:
        async with qual_db.transaction(conn) as t:
            if qual_db.dialect == "postgres":
                sql = (
                    f"UPDATE {table} SET state = 'claimed',"
                    " claimed_by = :worker, claimed_at = :now,"
                    " claimed_until = :until, claim_token = claim_token + 1,"
                    " updated_at = :now"
                    " WHERE id IN ("
                    f"  SELECT id FROM {table}"
                    f"  WHERE {state_clause} AND next_attempt_at <= :now"
                    " AND attempts < :max_attempts"
                    "  ORDER BY next_attempt_at, id"
                    "  LIMIT :limit"
                    "  FOR UPDATE SKIP LOCKED"
                    ")"
                )
                rows = await t.fetch_all(
                    sql, {**claimed_params, **state_params}
                )
                return rows

            # SQLite: bounded select-then-update under BEGIN IMMEDIATE.
            ids = [
                row["id"]
                for row in await t.fetch_all(
                    f"SELECT id FROM {table}"
                    f" WHERE {state_clause} AND next_attempt_at <= :now"
                    " AND attempts < :max_attempts"
                    " ORDER BY next_attempt_at, id LIMIT :limit",
                    {**claimed_params, **state_params},
                )
            ]
            if not ids:
                return []
            id_clause, id_params = _in_clause("id", ids)
            await t.execute(
                f"UPDATE {table} SET state = 'claimed',"
                " claimed_by = :worker, claimed_at = :now,"
                " claimed_until = :until, claim_token = claim_token + 1,"
                " updated_at = :now"
                f" WHERE {id_clause}",
                {**claimed_params, **id_params},
            )
            return await t.fetch_all(
                f"SELECT * FROM {table} WHERE {id_clause}", id_params
            )


def leased_write_sql(table: str, set_clause: str) -> str:
    """A leased queue write: claim_token CAS + live lease (sections 8.6/8.8)."""
    return (
        f"UPDATE {table} SET {set_clause}"
        " WHERE id = :id AND claim_token = :claim_token"
        " AND claimed_until > :now"
    )


async def leased_write(
    t: DomainTransaction, table: str, set_clause: str, params: dict
) -> None:
    """Perform one leased write; a lost CAS raises ``StaleClaim``."""
    rc = await t.execute(leased_write_sql(table, set_clause), params)
    if rc != 1:
        raise StaleClaim(
            f"leased write to {table} lost its claim-token CAS"
            f" (id={params.get('id')!r}, claim_token={params.get('claim_token')!r})"
        )


# --- Section 4.16 task leases + fencing ---


async def acquire_lease(
    t: DomainTransaction,
    table: str,
    *,
    name: str,
    holder: str,
    now: int,
    ttl_seconds: int,
) -> int:
    """Acquire or renew a task lease; returns the new fencing token.

    Renewal by the current holder, or takeover after ``leased_until``
    expiry, increments the monotonically increasing ``fencing_token``.
    A lease that is live and held by another worker raises ``LeaseHeld``
    (the INSERT hits the PRIMARY KEY).
    """
    params = {"name": name, "holder": holder, "now": now, "until": now + ttl_seconds}
    rc = await t.execute(
        f"UPDATE {table} SET holder_id = :holder,"
        " fencing_token = fencing_token + 1, leased_until = :until,"
        " updated_at = :now"
        " WHERE name = :name AND (leased_until <= :now OR holder_id = :holder)",
        params,
    )
    if rc == 1:
        rows = await t.fetch_all(
            f"SELECT fencing_token FROM {table} WHERE name = :name",
            {"name": name},
        )
        return int(rows[0]["fencing_token"])
    try:
        await t.execute(
            f"INSERT INTO {table}"
            " (name, holder_id, fencing_token, leased_until, updated_at)"
            " VALUES (:name, :holder, 1, :until, :now)",
            params,
        )
    except Exception as exc:  # noqa: BLE001 (IntegrityError across dialects)
        if "IntegrityError" in type(exc).__name__:
            raise LeaseHeld(f"task lease {name!r} is held by another worker") from exc
        raise
    return 1


def fenced_write_sql(table: str, set_clause: str, key_column: str = "name") -> str:
    """A fencing-token compare-and-swap write (section 4.16)."""
    return (
        f"UPDATE {table} SET {set_clause}"
        f" WHERE {key_column} = :key AND fencing_token = :fencing_token"
    )


async def fenced_write(
    t: DomainTransaction,
    table: str,
    set_clause: str,
    params: dict,
    key_column: str = "name",
) -> None:
    """Perform one fenced write; a stale token raises ``StaleFencingToken``."""
    sql = fenced_write_sql(table, set_clause, key_column)
    rc = await t.execute(sql, params)
    if rc != 1:
        raise StaleFencingToken(
            f"fenced write to {table} carried stale fencing_token"
            f" ({params.get('fencing_token')!r})"
        )
