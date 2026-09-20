"""Section 14 transaction adapter for the qualification harness.

One ``Database.connect()`` context per domain transaction; raw parameterized
statements only; explicit commit/rollback. The host's auto-committing
``Connection``/``Database`` helper methods (``execute``/``insert``/``update``)
are NEVER called inside a domain transaction — their use is forbidden by
section 14 and tested in plan 01-02.

Dialect paths (both verified against the pinned stack):

- SQLite: ``BEGIN IMMEDIATE`` on the raw aiosqlite connection, raw statements
  with named ``:param`` placeholders (sqlite3 native named-parameter style),
  explicit ``commit()``/``rollback()`` on the raw connection.
- PostgreSQL: ``conn.conn.begin()`` (SQLAlchemy-managed transaction) with
  schema-qualified tables and raw ``text()``-level statements.

All statements use the SAME named-parameter ``:param`` spelling on both
dialects — sqlite3 binds dict parameters natively.
"""

from __future__ import annotations

from lnbits.db import Connection

from harness import db as db_module


class SagaConflict(Exception):
    """A section 8.2 step-1 saga precondition lost; the transaction rolled back."""


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
        " (id, product_id, order_id, quantity, state, expires_at)"
        " VALUES (:id, :product_id, :order_id, :qty, :state, :expires_at)"
    )


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
    """Section 8.2 step 1 as ONE transaction.

    Conditionally claims stock (guard: stock_on_hand - stock_reserved >= qty,
    product not deleted), transitions the order with compare-and-swap, and
    inserts a ``held`` reservation. If ANY rowcount != 1 the entire
    transaction rolls back and ``SagaConflict`` is raised — exactly one
    concurrent worker can win this transition.
    """
    async with qual_db.connect() as conn:
        async with qual_db.transaction(conn) as t:
            rc = await t.execute(
                claim_stock_sql(qual_db.table("products")),
                {"qty": qty, "product_id": product_id},
            )
            if rc != 1:
                raise SagaConflict(f"stock claim failed for product {product_id}")
            rc = await t.execute(
                cas_order_state_sql(qual_db.table("orders")),
                {
                    "to_state": to_state,
                    "order_id": order_id,
                    "from_state": from_state,
                },
            )
            if rc != 1:
                raise SagaConflict(f"order CAS failed for order {order_id}")
            await t.execute(
                insert_reservation_sql(qual_db.table("inventory_reservations")),
                {
                    "id": reservation_id,
                    "product_id": product_id,
                    "order_id": order_id,
                    "qty": qty,
                    "state": "held",
                    "expires_at": expires_at,
                },
            )
