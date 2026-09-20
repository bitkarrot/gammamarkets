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


class QualWorker:
    """An additional ``Database`` handle over the SAME underlying database.

    The host's ``Database.connect()`` serializes connections through one
    asyncio lock per ``Database`` object, so concurrency proofs (P0-06 last
    unit, section 8.2 parallel buyers) need one handle per parallel worker:
    each worker gets its own engine + lock while sharing the SQLite file or
    PostgreSQL schema. SQLite then serializes writers through BEGIN
    IMMEDIATE file locks; PostgreSQL through row locking (section 14).
    """

    def __init__(self, parent: "QualDatabase") -> None:
        self.dialect = parent.dialect
        self.schema = parent.schema
        self.name = parent.name
        self.database = Database(parent.name)

    def table(self, name: str) -> str:
        return f"{self.schema}.{name}" if self.schema else name

    @asynccontextmanager
    async def connect(self):
        async with self.database.connect() as conn:
            if self.dialect == _SQLITE:
                raw = raw_sqlite_connection(conn)
                await raw.execute("PRAGMA foreign_keys=ON")
            yield conn

    def transaction(self, conn: Connection):
        from harness import tx

        return tx.DomainTransaction(conn, self.dialect)

    async def fetch_all(self, sql: str, params: dict | None = None) -> list[dict]:
        from harness import tx

        async with self.connect() as conn:
            return await tx.fetch_all(conn, self.dialect, sql, params)


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
        self._workers: list[QualWorker] = []

    def table(self, name: str) -> str:
        """Schema-qualified table reference (PG) or bare name (SQLite)."""
        return f"{self.schema}.{name}" if self.schema else name

    @property
    def file_path(self) -> str | None:
        """The SQLite database file path (None on PostgreSQL).

        P0-09 uses it for the byte-level plaintext-absence search over the
        raw database file.
        """
        if self.dialect != _SQLITE:
            return None
        from lnbits.settings import settings

        return str(Path(settings.lnbits_data_folder) / f"{self.name}.sqlite3")

    def worker(self) -> QualWorker:
        """A parallel-worker handle over this same database (own engine+lock)."""
        worker = QualWorker(self)
        self._workers.append(worker)
        return worker

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
        for worker in self._workers:
            await worker.database.engine.dispose()
        self._workers.clear()
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
