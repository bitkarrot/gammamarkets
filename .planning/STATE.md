---
gsd_state_version: "1.0"
current_phase: 2
current_phase_name: Release A — Safe Web Commerce
status: executing
stopped_at: Phase 2 implementation, current-revision Linux CI and fresh demo verified; human UAT and security/accessibility sign-off pending
last_updated: "2026-09-27T07:36:11.000Z"
last_activity: 2026-09-27
last_activity_desc: Local suites, four blocking Linux CI profiles and the fresh 5099 demo passed; human release review remains open
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 7
  completed_plans: 7
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-20)

**Core value:** A merchant can sell one authoritative inventory safely through LNbits-backed web and Nostr flows without duplicate invoices, double allocation, or relay delivery being mistaken for payment truth.
**Current focus:** Phase 2 — Release A: Safe Web Commerce

## Current Position

Phase: 2 of 4 (Release A — Safe Web Commerce)
Plan: 4 plans written (02-01..02-04), checker-verified, 4/4 implemented
Status: Executing closeout — local and Linux CI passed, fresh 5099 demo deployed; human security/accessibility/UX review outstanding
Last activity: 2026-09-27 — four Linux matrix jobs passed on `b12e350`; new 5099 quote route and seven browser smoke checks passed

Progress: [██████████] 100% of written implementation plans; only Phase 1 of 4 is formally complete

## Performance Metrics

**Velocity:**

- Total plans completed: 6
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: none
- Trend: Not established

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 1 P01 | 20 min | 3 tasks | 23 files |
| Phase 01 P02 | 21 min | 3 tasks | 15 files |
| Phase 01 P03 | ~50 min | 3 tasks | 25 files |
| Phase 02 P01 | multi-session | 3 tasks | 18 created + 4 modified |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md and the normative specification.

- Runtime identity is `gammamarkets`.
- Direct qualified `nostr-sdk` is the baseline; other relay extensions are unqualified adapter candidates.
- GSD Phase 1 is the contract's Phase 0 evidence gate; it contains no production runtime implementation.
- Release order is A web commerce, B Gamma NIP-17, C legacy interop/migration.
- Checkout preserves Editorial/Guided/Compact merchant presets with responsive mobile fallback and invariant payment semantics.
- Merchant order operations use a split list/detail workspace with embedded chronology.
- Public themes use preset, Brand Basics, and guarded Advanced Tokens tiers; admin styling stays host-controlled.
- Phase 2 UI planning must load `.devin/skills/sketch-findings-gammamarkets/` and produce a binding UI contract.
- [Phase 1]: Plan 01-01 shipped the permanent qualification harness: pins/provenance (P0-01), SDK security boundary (P0-02), host contract boundary (P0-03), one canonical make verify + evidence bundle, CI blocking matrix. — Everything later phases build depends on the pinned host/SDK/database contract being proven reproducible; the harness is permanent regression infrastructure (D-05), not disposable qualification code.
- [Phase 1]: PG queue claims run as lock-select/update/fetch in one transaction with FOR UPDATE SKIP LOCKED: SQLAlchemy 1.4 + asyncpg returns no rows from raw text() UPDATE...RETURNING (01-02)
- [Phase 1]: Idempotent intent inserts use ON CONFLICT DO NOTHING with deterministic ids: PostgreSQL aborts transactions on constraint violations, so IntegrityError catch-and-continue is not dialect-portable (01-02)
- [Phase 1]: Outbox publication evidence is durable and append-only, recorded separately from the fenced claim-token outcome write: models the section 8.6 crash point and makes stale-claim reconstruction honest (01-02)
- [Phase 1]: Cancelled orders retain their payment projection for late-settlement detection; BOLT11 delivery and payment-request enqueue happen only for invoice_pending orders (spec 8.2 step 3, decision 24)
- [Phase 2]: Host `deactivate_all` is a persisted editable admin setting — runtime fixtures must reset it in the shared core DB, and `sys.modules` must be purged before re-import so `Database()` binds the right data folder (02-01)
- [Phase 2]: Host `rewrite_values` HTML-strips raw execute/fetch params — markdown/JSON payloads only persist via `insert`/`update` or DomainTransaction raw statements (02-01)
- [Phase 2]: Cookie auth wins when a request carries both cookie and bearer headers — prevents bearer bypass of Origin/CSRF (02-01)
- [Phase 2]: Kind-5 tombstone intents carry the bumped aggregate revision so supersession retires stale pending publishes; product intents enqueue AFTER collection republishes so dependency edges bind to live rows (02-01)

### Release Closeout Gates

- [x] Current-revision Linux x86_64 and ARM64 CI for SQLite and PostgreSQL passed: run 36303338957 on `b12e350`.
- [ ] Human buyer/merchant UAT and security/accessibility sign-off in `02-UAT.md` and `02-SECURITY.md`.
- [x] At the user's request, the 5099 demo was replaced with a fresh seed; quote returned HTTP 200 and buyer/admin browser smoke checks passed. Old disposable database files were not deleted, but are not mounted in the new demo.

### Blockers/Concerns

- Phase 2 automated local and Linux verification passed, but human sign-off is still outstanding; Phase 2 is not formally complete (`02-VERIFICATION.md`).
- The new demo uses a fresh disposable database rather than migrating old demo orders and the previously hand-added images. If those records must remain visible, the old database requires a separate recovery plan.
- Release B cannot claim production readiness without deployed egress controls and external-client evidence.
- Release C requires a live scarce-stock payable-invoice cutover rehearsal.

## Deferred Items

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| Protocol | NIP-37 draft synchronization | Deferred | Initialization | v2 |
| Commerce | Subscriptions, preorder purchasing, automated refunds | Deferred | Initialization | v2 |
| Transport | `nostrclient`/`nostrrelay` runtime adapters | Qualification required | Initialization | Future |

## Session Continuity

Last session: 2026-09-27T07:36:11.000Z
Stopped at: Phase 2 implementation, Linux CI and fresh demo verified; human UAT/security/accessibility sign-off pending
Resume file: .planning/phases/02-release-a-safe-web-commerce/02-VERIFICATION.md
