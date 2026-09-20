"""Pytest configuration for the GammaMarkets qualification harness.

Session-start env conventions (set before any ``lnbits`` import):

- ``LNBITS_DATABASE_URL`` selects the database dialect exactly like the
  pinned host (unset/empty = SQLite profile). It is read once at session
  start; only the dialect NAME is ever recorded in evidence (credentials
  never are).
- ``LNBITS_DATA_FOLDER`` defaults into the gitignored ``.cache/`` so
  importing ``lnbits.db`` never creates ``./lnbits/`` in the repo root.
- ``GAMMA_QUAL_LNBITS_DIR`` defaults to ``.cache/lnbits`` (the harness-owned
  pinned checkout; never the read-only research copy).
- ``LNBITS_BACKEND_WALLET_CLASS=FakeWallet`` and a tmp data folder are
  applied ONLY inside host fixtures (see ``host_settings_overrides``),
  mirroring the pinned host's own tests/conftest.py.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- session-start env conventions (before any lnbits import) ---------------
os.environ.setdefault(
    "LNBITS_DATA_FOLDER", str(REPO_ROOT / ".cache" / "qual-data")
)
os.environ.setdefault(
    "GAMMA_QUAL_LNBITS_DIR", str(REPO_ROOT / ".cache" / "lnbits")
)
# LNBITS_DATABASE_URL is read once here at session start; the harness never
# re-reads it (the host fixes the dialect at import time).
LNBITS_DATABASE_URL = os.environ.get("LNBITS_DATABASE_URL", "").strip()

from harness import evidence  # noqa: E402  (imports lnbits with env set)
from harness.db import QualDatabase  # noqa: E402

MARKERS = {
    "fast": "quick local checks (pins and provenance)",
    "sdk": "nostr-sdk security/FFI/crypto probes",
    "db": "database transaction and state probes",
    "protocol": "Nostr protocol-level probes (deterministic local relays)",
    "host": "LNbits host contract probes (boots the pinned host app)",
}


def pytest_configure(config):
    for name, helptext in MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {helptext}")
    # Register the evidence plugin (D-09): normalized manifest + report.
    config.pluginmanager.register(evidence, "gamma-evidence")


def host_settings_overrides(data_folder: Path | str) -> dict:
    """Settings overrides applied ONLY inside host app fixtures.

    Mirrors the pinned host's tests/conftest.py: FakeWallet funding source
    and an isolated tmp data folder. These are applied to the mutable
    ``lnbits.settings`` singleton (not process env) by harness/host.py.
    """
    return {
        "lnbits_backend_wallet_class": "FakeWallet",
        "lnbits_data_folder": str(data_folder),
    }


@pytest.fixture(scope="session")
def qual_db_factory():
    """Session-scoped fixture factory yielding a fresh schema database per use.

    Each call creates a fresh QualDatabase (SQLite: unique tmp file via the
    host Database class; PostgreSQL: unique schema selected by
    LNBITS_DATABASE_URL) with the harness DDL applied, and tears it down on
    exit — one fresh database per test.
    """

    @asynccontextmanager
    async def make_database():
        qual_db = await QualDatabase().create()
        try:
            yield qual_db
        finally:
            await qual_db.teardown()

    return make_database
