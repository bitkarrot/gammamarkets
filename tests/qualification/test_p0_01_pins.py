"""P0-01 (tracer scope): pin and provenance verification.

Asserts the installed SDK identity, the Python 3.12-only claim (D-02), the
pinned host checkout revision (D-01), and the initial PINS.md pin freeze.

Plan Task 2 extends this module with host-lock wheel-hash parity, native
library hash recording, sdist/Cargo provenance, and the full platform-matrix
assertions.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import sys
import tomllib
from pathlib import Path

import pytest

from tools.checkout_host import LNBITS_COMMIT, host_checkout_dir, read_head

pytestmark = pytest.mark.fast

REPO_ROOT = Path(__file__).resolve().parents[2]
PINS_MD = REPO_ROOT / "PINS.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

EXPECTED_NOSTR_SDK = "0.44.8"


def test_installed_nostr_sdk_is_exactly_pinned():
    assert importlib_metadata.version("nostr-sdk") == EXPECTED_NOSTR_SDK


def test_requires_python_is_3_12_only():
    with PYPROJECT.open("rb") as fh:
        pyproject = tomllib.load(fh)
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"


def test_running_interpreter_is_3_12():
    assert sys.version_info[:2] == (3, 12), (
        "the qualification profile claims Python 3.12 only (D-02)"
    )


def test_host_checkout_head_is_pinned_commit():
    head = read_head(host_checkout_dir())
    assert head == LNBITS_COMMIT, (
        f"host checkout must be exactly {LNBITS_COMMIT}, found {head} "
        "(no silent downgrade, D-01)"
    )


@pytest.mark.parametrize(
    ("needle", "what"),
    [
        ("5dc79c5", "GammaMarkets market-spec pin"),
        (
            "a2494f4f81d46684e5814a9bf35e2b1df978f955",
            "Nostr NIPs pin",
        ),
        ("v2 payload only", "NIP-44 v2-only pin"),
        (
            "e336fe14b841d6f0c940e75b3d343e3ab5cf8433",
            "LNbits commit pin",
        ),
        ("v1.6.2-rc1", "LNbits tag"),
        (EXPECTED_NOSTR_SDK, "nostr-sdk candidate pin"),
        ("Linux x86_64", "blocking platform (x86_64)"),
        ("Linux ARM64", "blocking platform (ARM64)"),
        ("PostgreSQL", "blocking database"),
        ("SQLite", "blocking database"),
        ("macOS ARM64", "advisory smoke profile"),
        ("Python 3.12 only", "Python 3.12-only claim (D-02)"),
        ("PENDING", "approval section (D-11)"),
    ],
)
def test_pins_md_records_the_pinned_identities(needle: str, what: str):
    text = PINS_MD.read_text()
    assert needle in text, f"PINS.md must record the {what}"
