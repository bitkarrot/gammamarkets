---
gsd_state_version: "1.0"
current_phase: 1
current_phase_name: Conformance Profile
status: planning
stopped_at: Phase 1 context gathered
last_updated: "2026-09-20T05:12:37.617Z"
last_activity: 2026-09-20
last_activity_desc: UI research completed; three interactive sketch decisions packaged for Phase 2
state_head: 9e44079c3b3619973b45b85b44551e7a5a0c5d21
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-20)

**Core value:** A merchant can sell one authoritative inventory safely through LNbits-backed web and Nostr flows without duplicate invoices, double allocation, or relay delivery being mistaken for payment truth.
**Current focus:** Phase 1 — Conformance Profile (Contract Phase 0)

## Current Position

Phase: 1 of 4 (Conformance Profile)
Plan: 0 of 3 in current phase
Status: Ready to discuss and plan
Last activity: 2026-09-20 — UI research completed; three interactive sketch decisions packaged for Phase 2

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

Last session: 2026-09-20T05:12:37.603Z
Stopped at: Phase 1 context gathered
Resume file: .planning/phases/01-conformance-profile-contract-phase-0/01-CONTEXT.md
