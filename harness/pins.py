"""Pin recording for the qualification evidence bundle.

Task 1 scope: the recording helper for the tested nostr-sdk binary identity
(installed native library filename + SHA-256) plus the default pin snapshot
(nostr-sdk version, pinned LNbits checkout commit). Plan Task 2 extends this
module with host-lock wheel parsing, full lock-resolution recording, and
sdist/Cargo provenance.

Everything recorded here flows into the evidence manifest pins block via
``harness.evidence``; the raw ``LNBITS_DATABASE_URL`` is never recorded
(it may carry credentials).
"""

from __future__ import annotations

import hashlib
import importlib.metadata as importlib_metadata
import importlib.util
from pathlib import Path

# The pinned host revision (spec section 2). tools/checkout_host.py owns the
# checkout; this module only reads it.
LNBITS_COMMIT = "e336fe14b841d6f0c940e75b3d343e3ab5cf8433"
LNBITS_TAG = "v1.6.2-rc1"
NOSTR_SDK_VERSION = "0.44.8"

NATIVE_LIBRARY_SUFFIXES = (".so", ".dylib", ".pyd")

# Pins recorded during the run; ``harness.evidence`` snapshots this at
# session finish. Tests record values here via ``record``/``record_tested_binary``.
_RECORD: dict[str, object] = {}


def record(key: str, value: object) -> None:
    """Record a pin value into the evidence manifest pins block."""
    _RECORD[key] = value


def snapshot() -> dict[str, object]:
    """Return the pins recorded so far (defaults merged in)."""
    ensure_defaults()
    return dict(_RECORD)


def nostr_sdk_version() -> str:
    """Installed nostr-sdk version per importlib.metadata."""
    return importlib_metadata.version("nostr-sdk")


def lnbits_checkout_head() -> str | None:
    """HEAD commit of the harness-owned LNbits checkout, or None if absent."""
    from tools.checkout_host import host_checkout_dir, read_head

    return read_head(host_checkout_dir())


def installed_native_libraries() -> list[Path]:
    """Compiled library files inside the installed nostr-sdk package."""
    spec = importlib.util.find_spec("nostr_sdk")
    if spec is None or not spec.submodule_search_locations:
        return []
    package_dir = Path(list(spec.submodule_search_locations)[0])
    return sorted(
        p
        for p in package_dir.iterdir()
        if p.is_file() and p.suffix in NATIVE_LIBRARY_SUFFIXES
    )


def native_library_identity() -> dict[str, object]:
    """Identity (filename, size, sha256) of the installed native SDK library.

    This is the "tested binary" required by P0-02: the artifact whose FFI the
    probes actually exercised.
    """
    libs = installed_native_libraries()
    if not libs:
        raise RuntimeError(
            "no compiled nostr-sdk library found in the installed package"
        )
    lib = libs[0]
    data = lib.read_bytes()
    return {
        "filename": lib.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def record_tested_binary() -> dict[str, object]:
    """Record the tested native SDK binary identity into the pins block."""
    identity = native_library_identity()
    record("nostr_sdk_native_library", identity)
    return identity


def ensure_defaults() -> None:
    """Populate default pins (nostr-sdk version, LNbits checkout revision)."""
    _RECORD.setdefault("nostr_sdk", nostr_sdk_version())
    _RECORD.setdefault("lnbits_commit", lnbits_checkout_head())
    _RECORD.setdefault("lnbits_tag", LNBITS_TAG)
