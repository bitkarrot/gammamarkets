# PINS — GammaMarkets Qualification Profile

Frozen pins, platform claims, artifact identities, provenance, and evidence
pointers for the GammaMarkets conformance profile. Surfaced per technical
specification section 2 (Pinned inputs). Any candidate other than the
host-resolved `nostr-sdk==0.44.8` requires an explicit spec decision and the
identical qualification profile (D-13, D-14). The host MUST NOT be silently
downgraded.

**Status: PENDING OWNER APPROVAL** (D-11) — see [Approval](#approval).

---

## 1. Normative Pins

| Input | Pin |
|---|---|
| GammaMarkets market-spec | commit `5dc79c5` (`main` @ 2025-05-10) |
| Nostr NIPs | commit `a2494f4f81d46684e5814a9bf35e2b1df978f955` (2026-09-09); files 09, 15, 17, 32, 37, 42, 44, 59, 65, 89, 99 |
| NIP-15 status | draft/unrecommended — compatibility only |
| NIP-44 version | v2 payload only |
| Nostr library (Phase 0 candidate) | Python `nostr-sdk==0.44.8` — host-resolved; a candidate, not a safety certification |
| LNbits host | `v1.6.2-rc1`, commit `e336fe14b841d6f0c940e75b3d343e3ab5cf8433` (Python >=3.10,<3.13) |

Version `0.44.8` is a candidate because the pinned host resolves it, not a
safety certification by version number (spec section 2).

## 2. Platform Claim (D-01, D-02, D-03, D-04)

**Blocking profiles (all four must pass the complete suite clean — D-10):**

| # | Architecture | OS | Database |
|---|---|---|---|
| 1 | Linux x86_64 | ubuntu-24.04 | SQLite |
| 2 | Linux x86_64 | ubuntu-24.04 | PostgreSQL |
| 3 | Linux ARM64 | ubuntu-24.04-arm | SQLite |
| 4 | Linux ARM64 | ubuntu-24.04-arm | PostgreSQL |

**Advisory profile (non-blocking, D-04):** macOS ARM64 (SQLite smoke).
Failures are visible but do not block Release A; local developer runs on
macOS are advisory evidence only.

**Python claim (D-02):** Python 3.12 only (`>=3.12,<3.13`) — deliberately
narrower than the pinned LNbits host, which permits Python 3.10–3.12. The
extension's packaging metadata, startup/install checks, and release
documentation state this narrower claim explicitly.

## 3. SDK Artifact Identities (nostr-sdk 0.44.8)

Wheel filename and SHA-256 per platform tag are **parsed at verification
time from the pinned host checkout's `uv.lock`** (`.cache/lnbits/uv.lock`,
the source of truth for P0-01) — never hand-copied into prose. The
qualification suite (`tests/qualification/test_p0_01_pins.py`) verifies that
the harness's own lock resolves the same artifact hashes as the host lock
for the executing platform's tag; any parity mismatch blocks (no silent
downgrade, D-01).

Recorded identities (parsed from the host lock at pin-freeze time, for
review only — runtime verification re-parses the lock):

| Platform tag | Wheel | SHA-256 |
|---|---|---|
| manylinux_2_17_x86_64 | `nostr_sdk-0.44.8-cp39-abi3-manylinux_2_17_x86_64.whl` | `e6b2f1b44ae95b35712008c2e0335ab833a30545a80c4afa45992b439b20e66b` |
| manylinux_2_17_aarch64 | `nostr_sdk-0.44.8-cp39-abi3-manylinux_2_17_aarch64.whl` | `7b7a684afbfc9118aa2dd3adc7f06fa0d0f872e7ccfdf7542d2ba649f4b3689b` |
| macosx_11_0_arm64 | `nostr_sdk-0.44.8-cp39-abi3-macosx_11_0_arm64.whl` | `d781526da09550a8ca7b11abf0ee270bda53fabe191a2abfc8851dd1f3f4235c` |

musllinux, x86_64-macOS, and Windows wheel identities are also recorded in
the host lock; the complete set is parsed and compared by the P0-01 suite.

The host lock records **wheels only** for `nostr-sdk` (no sdist entry).
Release-source (sdist) provenance and native Cargo dependency revisions are
recorded by the P0-01 provenance extension (plan 01-01 Task 2).

## 4. Installation / Lockfile Path (supported, reproducible)

```text
tools/checkout_host.py   # idempotent; hard-fails unless HEAD == e336fe14b841d6f0c940e75b3d343e3ab5cf8433
uv sync                  # resolves lnbits (path source) + nostr-sdk==0.44.8 into uv.lock
make verify              # canonical verification command (D-07)
```

- Harness lockfile: `uv.lock` (repo root) — identity recorded in the
  evidence manifest pins block.
- Host checkout: `.cache/lnbits` at commit
  `e336fe14b841d6f0c940e75b3d343e3ab5cf8433` (gitignored; content-addressed
  verification on every run).
- The read-only research checkout at
  `/Users/bk/github/gamma-markets-research/lnbits` (revision `74cccac`) is
  never used by the harness — it is not the qualified source.

## 5. Evidence Pointers (D-09)

- `evidence/manifest.json` — machine-readable normalized results (schema
  version, UTC timestamp, exact verify command, profile block, pins block,
  per-test results, P0-01..P0-14 coverage map).
- `evidence/REPORT.md` — concise human report rendered from the manifest
  (profile, pins summary, P0 coverage table, failures, D-16 disclosure).
- CI artifacts (raw pytest output) are uploaded per profile job by
  `.github/workflows/qualification.yml`; raw output is never committed.
- Reruns do not flip recorded outcomes (D-10 clean-pass policy): the tooling
  performs single runs only.

## 6. Approval

**PENDING** — explicit owner approval of these pins and the evidence summary
is required before Phase 2 planning begins (D-11). Clean CI alone does not
unlock Release A planning.

| Field | Value |
|---|---|
| Approved pins | _pending_ |
| Approved evidence bundle | _pending_ |
| Owner / date | _pending_ |
