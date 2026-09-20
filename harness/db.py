"""Dialect-switching database support for the qualification harness.

The database dialect is selected by ``LNBITS_DATABASE_URL`` exactly like the
pinned host (unset/empty = SQLite profile). Each test gets a FRESH database:

- SQLite profile: a unique plain-named ``Database`` (tmp file under
  ``LNBITS_DATA_FOLDER``). A plain name is deliberate: the host's ``ext_``
  prefix ATTACHes the same file under a schema alias, and SQLite rejects
  ``BEGIN IMMEDIATE`` on a connection that attached the same file twice
  ("database is locked") — verified against the pinned stack. Tables are
  referenced unqualified.
- PostgreSQL profile: a unique ``ext_``-prefixed ``Database``; the host
  creates the schema on connect, and tables are schema-qualified per section 14.

The raw ``LNBITS_DATABASE_URL`` is never recorded — only the dialect name.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from lnbits.db import Connection, Database

REPO_ROOT = Path(__file__).resolve().parent.parent

_SQLITE = "sqlite"
_POSTGRES = "postgres"


def database_url() -> str:
    """LNBITS_DATABASE_URL as set in the environment (may be empty)."""
    return os.environ.get("LNBITS_DATABASE_URL", "").strip()


def dialect_name() -> str:
    """Selected dialect name: 'sqlite' or 'postgres'. Never the raw URL."""
    url = database_url()
    if url.startswith(("postgres://", "postgresql://", "postgresql+")):
        return _POSTGRES
    if url.startswith("cockroachdb://"):
        raise RuntimeError(
            "CockroachDB is not a v1 qualification target (spec section 14)"
        )
    return _SQLITE


def is_postgres() -> bool:
    return dialect_name() == _POSTGRES


def raw_sqlite_connection(conn: Connection):
    """The raw aiosqlite connection behind a host Connection (SQLite profile).

    The host wraps an SQLAlchemy 1.4 AsyncConnection; the raw driver
    connection is required for ``BEGIN IMMEDIATE`` (section 14 SQLite path).
    """
    return (
        conn.conn.sync_connection.connection.dbapi_connection._connection  # noqa: SLF001
    )


class QualDatabase:
    """A fresh schema database per test (SQLite: tmp file; PostgreSQL: schema)."""

    def __init__(self) -> None:
        self.dialect = dialect_name()
        token = uuid4().hex[:12]
        if self.dialect == _SQLITE:
            # Plain name: file at LNBITS_DATA_FOLDER/gamma_qual_<token>.sqlite3.
            self.name = f"gamma_qual_{token}"
            self.schema: str | None = None
        else:
            # ext_ prefix: host Database.connect() runs CREATE SCHEMA IF NOT EXISTS.
            self.name = f"ext_gamma_qual_{token}"
            self.schema = f"gamma_qual_{token}"
        self.database = Database(self.name)

    def table(self, name: str) -> str:
        """Schema-qualified table reference (PG) or bare name (SQLite)."""
        return f"{self.schema}.{name}" if self.schema else name

    @asynccontextmanager
    async def connect(self):
        """Yield a host Connection with SQLite FK enforcement enabled."""
        async with self.database.connect() as conn:
            if self.dialect == _SQLITE:
                # FK enforcement is per-connection in SQLite (P0-06 requirement).
                raw = raw_sqlite_connection(conn)
                await raw.execute("PRAGMA foreign_keys=ON")
            yield conn

    async def create(self) -> "QualDatabase":
        """Apply the harness DDL (outside any domain transaction)."""
        from harness import schema

        async with self.connect() as conn:
            for stmt in schema.ddl(self.dialect, self.schema):
                if self.dialect == _SQLITE:
                    raw = raw_sqlite_connection(conn)
                    await raw.execute(stmt)
                    await raw.commit()
                else:
                    # Host helper (auto-commits) — legal for DDL outside
                    # domain transactions; forbidden inside them (section 14).
                    await conn.execute(stmt)
        return self

    async def teardown(self) -> None:
        """Dispose the engine and remove the per-test database."""
        await self.database.engine.dispose()
        if self.dialect == _SQLITE:
            from lnbits.settings import settings

            path = Path(settings.lnbits_data_folder) / f"{self.name}.sqlite3"
            if path.exists():
                path.unlink()
        else:
            # Drop the per-test schema via a fresh connect.
            async with self.database.connect() as conn:
                await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')

    def transaction(self, conn: Connection):
        """A section-14 domain transaction on an open host Connection."""
        from harness import tx

        return tx.DomainTransaction(conn, self.dialect)

    async def fetch_all(self, sql: str, params: dict | None = None) -> list[dict]:
        """Read rows outside any domain transaction (commit-hygienic)."""
        from harness import tx

        async with self.connect() as conn:
            return await tx.fetch_all(conn, self.dialect, sql, params)
