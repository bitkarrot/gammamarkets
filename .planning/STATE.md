---
gsd_state_version: "1.0"
current_phase: 1
current_phase_name: Conformance Profile
status: Ready to discuss and plan
stopped_at: "Completed 01-03-PLAN.md (protocol fixtures + closure gate: P0-04/05/11/12/13/14)"
last_updated: "2026-09-20T19:46:03.218Z"
last_activity: 2026-09-20
state_head: e78caaa00d056f4037a7e710cd396043ee15ba73
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 3
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-20)

**Core value:** A merchant can sell one authoritative inventory safely through LNbits-backed web and Nostr flows without duplicate invoices, double allocation, or relay delivery being mistaken for payment truth.
**Current focus:** Phase 1 — Conformance Profile (Contract Phase 0)

## Current Position

Phase: 1 of 4 (Conformance Profile)
Plan: 3 of 3 in current phase
Status: Ready to discuss and plan
Last activity: 2026-09-20

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

- SDK `0.44.8` is a candidate, not an approved binary, until QUAL-01 through QUAL-03 pass.
- Release B cannot claim production readiness without deployed egress controls and external-client evidence.
- Release C requires a live scarce-stock payable-invoice cutover rehearsal.

## Deferred Items

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| Protocol | NIP-37 draft synchronization | Deferred | Initialization | v2 |
| Commerce | Subscriptions, preorder purchasing, automated refunds | Deferred | Initialization | v2 |
| Transport | `nostrclient`/`nostrrelay` runtime adapters | Qualification required | Initialization | Future |

## Session Continuity

Last session: 2026-09-20T07:24:15.389Z
Stopped at: Completed 01-03-PLAN.md (protocol fixtures + closure gate: P0-04/05/11/12/13/14)
Resume file: None
