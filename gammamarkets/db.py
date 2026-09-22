"""Extension database handle + section-14 transaction adapter.

Conventions (verified against the pinned host, e336fe1):

- ``Database("ext_gammamarkets")`` maps to the ``gammamarkets`` schema on
  PostgreSQL and to ``<data>/ext_gammamarkets.sqlite3`` on SQLite — where the
  host ``connect()`` also ATTACHes that same file under the ``gammamarkets``
  alias, so ``gammamarkets.<table>`` resolves on the host connection too.
- ``Connection.execute``/``insert``/``update`` auto-commit. Domain writes that
  span statements MUST go through :func:`domain_tx` — never the helpers.
- On SQLite the host connection cannot run ``BEGIN IMMEDIATE`` (the same file
  is attached twice — verified harness finding), so domain transactions open
  a dedicated raw aiosqlite connection to the same file. SQLite file locking
  still serializes writers.
- ``db.connect()`` serializes through one asyncio.Lock per Database object:
  concurrent workers call :func:`worker_db` for their own handle.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from lnbits.db import COCKROACH, POSTGRES, SQLITE, Connection, Database

SCHEMA = "gammamarkets"

db = Database("ext_gammamarkets")


def worker_db() -> Database:
    """A separate ``Database`` handle over the same extension database.

    ``Database.connect()`` serializes on a per-object lock, so every
    concurrent worker (outbox publisher, email sender, ...) owns its own
    handle — same file on SQLite, same schema on PostgreSQL.
    """
    return Database("ext_gammamarkets")


def table(name: str) -> str:
    """Schema-qualified table reference for host-connection SQL.

    ``gammamarkets.<name>`` resolves on both dialects: a real schema on
    PostgreSQL, the ATTACH alias on SQLite.
    """
    return f"{SCHEMA}.{name}"


def dialect() -> str:
    if db.type == POSTGRES:
        return "postgres"
    if db.type == COCKROACH:
        return "cockroachdb"
    return "sqlite"


def topology() -> str:
    """Deployment topology per spec section 14 / decision 15."""
    return dialect()


def topology_supported() -> tuple[bool, str | None]:
    """Refuse unsupported topologies (section 14).

    SQLite is single-process only; CockroachDB is not a v1 target. SQLite
    multi-process is not detectable from inside the process — the extension
    refuses only what it can prove (documented residual).
    """
    if dialect() == "cockroachdb":
        return False, "cockroachdb is not a supported v1 topology"
    return True, None


@asynccontextmanager
async def connect() -> AsyncIterator[Connection]:
    """Host connection for single-statement reads/writes (auto-commit).

    Foreign-key enforcement is per-connection on SQLite — enabled here so
    every consumer of this helper gets it.
    """
    async with db.connect() as conn:
        if db.type == SQLITE:
            await _raw_sqlite(conn).execute("PRAGMA foreign_keys=ON")
        yield conn


def _raw_sqlite(conn: Connection):
    """The raw aiosqlite connection behind a host Connection."""
    return (
        conn.conn.sync_connection.connection.dbapi_connection._connection  # noqa: SLF001
    )


class DomainTransaction:
    """One section-14 domain transaction: explicit begin/commit/rollback.

    - PostgreSQL: ``conn.conn.begin()`` on a host ``Database.connect()``
      context; tables referenced schema-qualified (``gammamarkets.x``).
    - SQLite: a dedicated raw aiosqlite connection to the extension file with
      ``BEGIN IMMEDIATE``; tables referenced unqualified (the file's ``main``
      schema is the extension database). The host connection's double-attach
      makes ``BEGIN IMMEDIATE`` fail there — this raw connection is the
      verified path.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._db = database or db
        self._dialect = dialect() if database is None else (
            "postgres"
            if database.type == POSTGRES
            else "cockroachdb"
            if database.type == COCKROACH
            else "sqlite"
        )
        self._host_conn_cm = None
        self._pg_tx = None
        self._raw = None

    async def __aenter__(self) -> "DomainTransaction":
        if self._dialect == "sqlite":
            import aiosqlite

            self._raw = await aiosqlite.connect(self._db.path)
            await self._raw.execute("PRAGMA foreign_keys=ON")
            await self._raw.execute("PRAGMA busy_timeout=5000")
            await self._raw.execute("BEGIN IMMEDIATE")
        else:
            self._host_conn_cm = self._db.connect()
            conn = await self._host_conn_cm.__aenter__()
            self._conn = conn
            self._pg_tx = await conn.conn.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            if self._raw is not None:
                await self._raw.close()
            if self._host_conn_cm is not None:
                await self._host_conn_cm.__aexit__(None, None, None)
        return None

    def table(self, name: str) -> str:
        """Table reference inside this transaction (schema on PG, bare on
        the raw SQLite connection)."""
        return f"{SCHEMA}.{name}" if self._dialect != "sqlite" else name

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

    async def fetch_all(
        self, sql: str, params: dict | None = None
    ) -> list[dict]:
        if self._raw is not None:
            cursor = await self._raw.execute(sql, params or {})
            columns = [d[0] for d in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        from sqlalchemy.sql import text

        result = await self._conn.conn.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]

    async def fetch_one(
        self, sql: str, params: dict | None = None
    ) -> dict | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None
