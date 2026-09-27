---
phase: 02-release-a-safe-web-commerce
verified: 2026-09-27T07:36:11Z
status: blocked
score: 5/5 local acceptance areas exercised; 4/4 Linux CI profiles passed; human review pending
covered_files:
  - .planning/phases/02-release-a-safe-web-commerce/02-01-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-02-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-03-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-04-SUMMARY.md
  - .planning/phases/02-release-a-safe-web-commerce/02-SECURITY.md
  - evidence/manifest.json
  - evidence/REPORT.md
behavior_unverified: 1
---

# Phase 2 — Release A Verification

**Verdict: implementation, local checks, required Linux CI and the fresh demo passed; Phase 2 is NOT formally complete or release-approved.** Human buyer/merchant UAT and security/accessibility sign-off remain open. The Phase 2 requirement statuses in `REQUIREMENTS.md` remain Pending.

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
| [Linux CI run 36303338957](https://github.com/bitkarrot/gammamarkets/actions/runs/36303338957) on `b12e350` | **x86_64 and ARM64 passed** | **x86_64 and ARM64 passed** |
| Ruff + JS syntax checks | `make lint` passed; changed browser modules passed `node --check` | CI lint passed |

The canonical results supersede the older 171-runtime/391-full/12-browser numbers in the 02-04 implementation summary. Both profiles ran the full 450-case tree **after** the invoice correlation, copy and 16-image gallery changes. Skips are the optional external-relay smoke plus two PostgreSQL-only concurrency drills on SQLite, or the optional smoke plus one SQLite-only cancellation drill on PostgreSQL. The isolated browser suites exercised the same extension against both databases, including a real local relay ACK path. PostgreSQL's 13-case Chromium run preceded only the final gallery-cap/scroll change; its new 16-image server-rendered behavior passed the PostgreSQL runtime test after that change. The PostgreSQL harness needed a dialect-portable boolean literal and schema-qualified seed SQL; those fixes remained in `tools/e2e_server.py`, not LNbits.

## Goal checks

| Phase 2 success criterion | Local evidence | Release status |
|---------------------------|----------------|----------------|
| Merchant identity/wallet, canonical catalog, shipping, theme and per-relay publication | Runtime catalog/outbox/theme tests on both dialects; admin browser surfaces and LocalRelay activation | Local and Linux CI pass; human merchant review pending |
| Local NIP-89 browse, authoritative total, one invoice, private order status | Quote and `expected_total_sat` share server pricing; buyer browser flows and payment token fragment stripping/header-only status | Local and Linux CI pass; human UI sign-off pending |
| Concurrency, duplicate, mismatched, expired and late payment preserve inventory | Transactional quota and conditional stock tests, reconciliation and new pre-delivery signed-invoice/host-wallet tests; no invoice reissue on uncertainty | Local and Linux CI pass; human exception review pending |
| Legal merchant order management and notifications | Order admin, queue, worker fencing and retention regressions plus split-workspace browser check | Local and Linux CI pass; human workflow review pending |
| Security, WCAG theme pairs, responsive layout, topology and Phase 0 assertions | `02-SECURITY.md` register (25 locally mitigated), contrast tests, compact browser test, UTC readiness guard, all applicable P0 probes | Local and Linux CI pass; human security/accessibility review pending |

## Completed external checks

1. **Linux CI:** [run 36303338957](https://github.com/bitkarrot/gammamarkets/actions/runs/36303338957) completed successfully on pushed commit `b12e350a5bfe651b2478d63129364663af1165b1`: x86_64 and ARM64 each passed SQLite and PostgreSQL qualification; lint and advisory macOS also passed. The run uploaded per-profile evidence artifacts.
2. **New demo:** at the user's request, the old 5099 process was stopped and a fresh SQLite/FakeWallet demo started with the current extension code. The previous temporary database files were not deleted but are **not mounted** in this new seed. On port 5099, product and storefront returned HTTP 200; `POST /gammamarkets/api/v1/public/quote` returned HTTP 200 with subtotal 2,500, shipping 0 and total 2,500 sats. Seven targeted Chromium buyer/admin smoke tests passed without creating or settling an order, using `GM_E2E_BASE_URL=https://localhost:5099` and `GM_E2E_SEED_PATH=.cache/phase2-demo-5099-20260927.seed.json` (the default `.seed.json` belongs to the old demo). Isolated full browser suites on ports 5110 and 5111 remain separate evidence, not human UAT.

## Remaining release gate

**Human security, accessibility and buyer/merchant UX sign-off:** automated checks do not establish keyboard/screen-reader usability or merchant workflow acceptance. All three tests in `02-UAT.md` still await the user's observations, and `02-SECURITY.md` remains draft despite 25 locally mitigated planned threats and green Linux CI. Until the required human review is recorded, Phase 2 requirements remain Pending.

Optional external public-relay smoke and real-funding-provider payment tests were not performed; LocalRelay ACK and FakeWallet are the stated local scope. The first PostgreSQL browser seed stopped on an SQLite-only boolean literal, leaving its disposable `gm_phase2_browser_utc` database untouched; the successful run used a new UTC-configured `gm_phase2_browser_v2_utc` database.

**Decision:** do not check off Phase 2 as complete or advance to Phase 3 until buyer/merchant UAT and human security/accessibility review are explicitly recorded. Fresh demo replacement, not data migration, was the user's requested deployment choice; old demo records are preserved on disk but are not visible in the new demo.
