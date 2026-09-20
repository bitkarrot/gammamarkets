"""Minimal normative schema subset for the transaction-model probes.

Only the tables the section 8.2 step-1 saga needs (per spec section 4.3/4.7/
4.12): ``products`` (id, stock_on_hand NULL-able, stock_reserved, deleted_at),
``orders`` (id, merchant_id, state), ``inventory_reservations`` (id,
product_id FK, order_id FK, quantity > 0, state, expires_at).

Dialect notes (verified against the pinned stack):

- SQLite: tables and FK references are unqualified. SQLite rejects
  schema-qualified ``REFERENCES schema.table(id)`` (parse error), and the
  harness SQLite database is a plain (non-``ext_``) host database.
- PostgreSQL: tables and FK references are schema-qualified; PostgreSQL
  resolves FK targets via search_path, not the referencing table's schema.
- Timestamps are stored as BIGINT unix epochs: dialect-appropriate 64-bit
  integers avoid the deprecated sqlite3 datetime adapters and asyncpg
  timezone pitfalls while staying orderable in SQL.
"""

from __future__ import annotations


def ddl(dialect: str, schema: str | None) -> list[str]:
    """DDL statements for the minimal normative subset.

    ``schema`` is the PostgreSQL schema name (None on SQLite).
    """

    def t(table: str) -> str:
        return f"{schema}.{table}" if schema else table

    # FK targets must match the table qualification rules described above.
    def fk(table: str) -> str:
        return f"{schema}.{table}" if schema else table

    int_type = "BIGINT" if dialect == "postgres" else "INTEGER"
    ts_type = "BIGINT" if dialect == "postgres" else "INTEGER"

    return [
        f"""
        CREATE TABLE {t("products")} (
            id TEXT PRIMARY KEY,
            stock_on_hand {int_type},
            stock_reserved {int_type} NOT NULL DEFAULT 0,
            deleted_at TEXT
        )
        """,
        f"""
        CREATE TABLE {t("orders")} (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            state TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE {t("inventory_reservations")} (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL REFERENCES {fk("products")}(id),
            order_id TEXT NOT NULL REFERENCES {fk("orders")}(id),
            quantity {int_type} NOT NULL CHECK (quantity > 0),
            state TEXT NOT NULL,
            expires_at {ts_type} NOT NULL
        )
        """,
    ]
