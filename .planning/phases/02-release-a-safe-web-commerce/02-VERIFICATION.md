---
phase: 02-release-a-safe-web-commerce
verified: 2026-09-27T07:23:43Z
status: blocked
score: 5/5 local acceptance areas exercised; external release gates pending
covered_files:
  - .planning/phases/02-release-a-safe-web-commerce/02-01-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-02-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-03-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-04-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-SECURITY.md
  - evidence/manifest.json
  - evidence/REPORT.md
behavior_unverified: 3
---

# Phase 2 — Release A Verification

**Verdict: implementation and local automated verification passed; Phase 2 is NOT formally complete or release-approved.** Four implementation plans exist, but current-revision Linux CI, human security/UX review and the stale live-demo deployment remain open. The Phase 2 requirement statuses in `REQUIREMENTS.md` remain Pending.

## Exact local profile

| Item | Value |
|------|-------|
| Tested date | 2026-09-27 UTC |
| Tested source | Implementation commit `5928ee9926f7508a34ff5835659b1074486ac6fc`, committed after testing with no code changes; its code/test/harness diff against `ccc7ef75f72f0573e3954486fac3865030324b42` has SHA-256 `f926b59c25bcba8b079f59cc3ac111a1c2381ceaa5b0b63c6653e8f97088fdff` |
| LNbits host | `1.6.2-rc1`, pinned checkout `e336fe14b841d6f0c940e75b3d343e3ab5cf8433`, clean `git status --short`; no core source changed |
| Language/OS | Python 3.12.13, Darwin arm64; this is **not** Linux ARM64 evidence |
| Payment backend | LNbits FakeWallet in a disposable host installation; no real-funds/provider claim |
| SQLite | Disposable test data directory; application tests plus localhost HTTPS Chromium on an isolated seed |
| PostgreSQL | Homebrew PostgreSQL 17.9, isolated test databases with session TimeZone UTC and process `TZ=UTC`; same pinned host/FakeWallet |
| Relay E2E | Owned local WebSocket test relay with positive ACK, not an external public-relay interoperability claim |

## Automated results

| Gate | SQLite | PostgreSQL |
|------|--------|------------|
| Canonical `make verify` (`GAMMA_QUAL_EVIDENCE=1 uv run pytest -q`) | **447 passed, 3 skipped** | **448 passed, 2 skipped**, 1 SQLAlchemy warning in the intentional host auto-commit probe |
| Runtime subset before the final invoice/gallery regressions | **224 passed, 2 skipped** | **225 passed, 1 skipped** |
| Focused mismatched amount/wallet invoice tests | **2 passed** | **2 passed** |
| Focused 16-image storefront page test | **1 passed** | **1 passed** |
| Chromium Playwright complete admin/buyer suite | **13 passed** | **13 passed** |
| Ruff + JS syntax checks | `make lint` passed; changed browser modules passed `node --check` | Same source |

The canonical results supersede the older 171-runtime/391-full/12-browser numbers in the 02-04 implementation summary. Both profiles ran the full 450-case tree **after** the invoice correlation, copy and 16-image gallery changes. Skips are the optional external-relay smoke plus two PostgreSQL-only concurrency drills on SQLite, or the optional smoke plus one SQLite-only cancellation drill on PostgreSQL. The isolated browser suites exercised the same extension against both databases, including a real local relay ACK path. PostgreSQL's 13-case Chromium run preceded only the final gallery-cap/scroll change; its new 16-image server-rendered behavior passed the PostgreSQL runtime test after that change. The PostgreSQL harness needed a dialect-portable boolean literal and schema-qualified seed SQL; those fixes remained in `tools/e2e_server.py`, not LNbits.

## Goal checks

| Phase 2 success criterion | Local evidence | Release status |
|---------------------------|----------------|----------------|
| Merchant identity/wallet, canonical catalog, shipping, theme and per-relay publication | Runtime catalog/outbox/theme tests on both dialects; admin browser surfaces and LocalRelay activation | Local pass; deployed relay/platform gate pending |
| Local NIP-89 browse, authoritative total, one invoice, private order status | Quote and `expected_total_sat` share server pricing; buyer browser flows and payment token fragment stripping/header-only status | Local pass; human UI sign-off pending |
| Concurrency, duplicate, mismatched, expired and late payment preserve inventory | Transactional quota and conditional stock tests, reconciliation and new pre-delivery signed-invoice/host-wallet tests; no invoice reissue on uncertainty | Local pass; Linux profiles pending |
| Legal merchant order management and notifications | Order admin, queue, worker fencing and retention regressions plus split-workspace browser check | Local pass; human workflow review pending |
| Security, WCAG theme pairs, responsive layout, topology and Phase 0 assertions | `02-SECURITY.md` register (25 locally mitigated), contrast tests, compact browser test, UTC readiness guard, all applicable P0 probes | Local pass; manual security/accessibility and CI pending |

## Unverified release gates

1. **Linux CI on the current revision:** the four required Linux x86_64/ARM64 × SQLite/PostgreSQL blocking profiles have not run with these unpushed changes. Phase 1's older green CI cannot substitute. A push requires an explicit request; no push was made here.
2. **Human security, accessibility and buyer/merchant UX sign-off:** automated checks do not prove keyboard/screen-reader experience or merchant workflow acceptance. `02-UAT.md` keeps these tests pending; `02-SECURITY.md` remains draft despite zero locally unmitigated planned threats.
3. **Existing demo deployment:** the still-running `https://localhost:5099` process predates `POST /gammamarkets/api/v1/public/quote` (verified 404). The updated static checkout fails closed there rather than displaying an unverified price. It must be replaced with the new host code using a data-preserving restart; it was not stopped or reset. Isolated updated test servers are available on ports 5110 (SQLite) and 5111 (PostgreSQL).

Optional external public-relay smoke and real-funding-provider payment tests were not performed; LocalRelay ACK and FakeWallet are the stated local scope. The first PostgreSQL browser seed stopped on an SQLite-only boolean literal, leaving its disposable `gm_phase2_browser_utc` database untouched; the successful run used a new UTC-configured `gm_phase2_browser_v2_utc` database. No existing tables or user demo data were deleted.

**Decision:** do not check off Phase 2 as complete, advance to Phase 3, or relabel these local macOS results as Linux CI. The release gate can be reconsidered after current-revision CI, safe demo deployment and human review are recorded.
