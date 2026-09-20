# Roadmap: gammamarkets

## Overview

The project advances through four gated vertical stages. GSD Phase 1 executes the normative contract's Phase 0 conformance profile without production runtime code. Phase 2 delivers safe Gamma/NIP-99 catalog publication and LNbits-backed web commerce. Phase 3 adds private Gamma NIP-17 orders after the commerce core is stable. Phase 4 adds literal NIP-15/NIP-04 interoperability and an inventory-liability-safe migration boundary.

## Phases

**Phase Numbering:**

- GSD integer phases are execution stages.
- GSD Phase 1 corresponds to the specification's named "Phase 0" qualification gate.
- Decimal phases are reserved for urgent inserted work.

- [x] **Phase 1: Conformance Profile (Contract Phase 0)** - Prove host, SDK, schema, state, security, and protocol assumptions before runtime implementation. (completed 2026-09-20)
- [ ] **Phase 2: Release A — Safe Web Commerce** - Ship catalog publication and LNbits-backed public checkout as the first production vertical slice.
- [ ] **Phase 3: Release B — Gamma NIP-17 Orders** - Add encrypted recipient-specific Gamma order messaging and external-client conformance.
- [ ] **Phase 4: Release C — Legacy Interop and Cutover** - Add literal NIP-15/NIP-04 compatibility and inventory-safe migration.

## Phase Details

### Phase 1: Conformance Profile (Contract Phase 0)

**Goal:** Produce reproducible evidence that the corrected contract can be implemented safely on the selected host/SDK/platform/topology profile.
**Mode:** mvp
**Depends on:** Nothing
**Requirements:** QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08, QUAL-09, QUAL-10, QUAL-11, QUAL-12, QUAL-13, QUAL-14
**Success Criteria** (what must be TRUE):

1. Exact host/SDK artifacts and native provenance are reproducible, and executable SDK security/FFI/crypto/ACK tests pass on every claimed platform.
2. Host invoice/listener/task/SMTP/auth/audit/FX probes pass with documented lifecycle and failure semantics.
3. SQLite and PostgreSQL executable models prove transaction atomicity, FK behavior, fencing, last-unit concurrency, cancellation/invoice recovery, and restart closure.
4. Protocol fixtures prove NIP-89 routing, NIP-17 wrap validation/routing, literal NIP-15 DTOs, and release-scoped compatibility restrictions.
5. P0-01 through P0-14 have recorded evidence and no undeclared state, field, route, identifier, or release dependency remains.

**Plans:** 3/3 plans complete

Plans:

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md
- [x] 01-03-PLAN.md
- [x] 01-01: Freeze pins, artifact provenance, and host/SDK contract harness
- [x] 01-02: Build executable state, transaction, fencing, crash, and notification models
- [x] 01-03: Build protocol, relay, auth/privacy, FX, and contract-closure fixtures

### Phase 2: Release A — Safe Web Commerce

**Goal:** A merchant can publish a protected Gamma/NIP-99 catalog and complete a safe LNbits-backed web order end to end.
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** MERC-01, CAT-01, CAT-02, PUB-01, PUB-02, WEB-01, WEB-02, PAY-01, PAY-02, INV-01, ORD-01, NOTF-01, SEC-01, UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):

1. Merchant can configure a protected identity/wallet, manage canonical catalog/inventory/shipping, select a bounded public layout/theme tier, and publish valid public events with visible per-relay outcomes.
2. Buyer can open the local NIP-89 handler, use an adaptive responsive checkout with a complete visible total, receive one correlated invoice, and poll private status without token leakage.
3. Concurrent, cancelled, expired, late, duplicated, and mismatched payment paths preserve stock and state invariants with no blind invoice reissue.
4. Merchant can triage and manage legal order/fulfillment/exception actions in a responsive split list/detail workspace with embedded chronology and per-recipient notifications.
5. Release-A security, accessibility/contrast, public/admin theme separation, retention, logging, unsupported-topology, failure-drill, and applicable Phase 0 assertions pass through the real implementation.

**Plans:** 3 plans
**UI prerequisite:** Before Phase 2 plan execution, generate and approve the Phase 2 UI contract using `.devin/skills/sketch-findings-gammamarkets/` and the normative technical specification.

Plans:

- [ ] 02-01: Extension skeleton, key custody, database/migrations, merchant and catalog domain
- [ ] 02-02: Public projection, relay outbox, NIP-89 catalog UI, tiered storefront themes, and publication health
- [ ] 02-03: Adaptive checkout, reservation, invoice saga, settlement, reconciliation, split order administration, and email

### Phase 3: Release B — Gamma NIP-17 Orders

**Goal:** A Nostr buyer can place and follow a Gamma order through declared inbox relays against the same canonical commerce authority.
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** GAM-01, GAM-02, GAM-03, GAM-04, GAM-05
**Success Criteria** (what must be TRUE):

1. Merchant activation publishes a valid kind-10050 profile only after configured inbox reachability is acknowledged.
2. Valid kind-16 orders enter the same pricing, inventory, invoice, settlement, and exception services as web checkout.
3. Payment, status, shipping, receipt, and general-message flows use verified NIP-17 chains, stable rumor identity, independent party copies, and declared-relay-only routing.
4. Inbox/outbox cursors, deduplication, overload handling, retry, sender recovery, and encrypted retention recover across crashes without duplicate domain commands.
5. Deployed egress controls, recipient-gated relay behavior, NIP-42, and an independent Gamma client conformance run pass before the Release-B claim.

**Plans:** 3 plans

Plans:

- [ ] 03-01: Merchant/peer inbox discovery, transport pools, NIP-42, and egress controls
- [ ] 03-02: NIP-17 inbox, order-message adapters, sender/recipient outbox copies, and recovery
- [ ] 03-03: External Gamma client interoperability, security drills, and Release-B verification

### Phase 4: Release C — Legacy Interop and Cutover

**Goal:** Existing NIP-15 merchants/clients can interoperate and migrate without turning legacy payable invoices into duplicate stock allocation.
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** LEG-01, LEG-02, LEG-03, LEG-04, LEG-05
**Success Criteria** (what must be TRUE):

1. Literal NIP-15 catalog and NIP-04 message fixtures round-trip through an external client with documented lossy mappings and physical-order restrictions.
2. Legacy orders use the canonical order/inventory/payment services and reject unsupported opaque-address physical checkout before reservation.
3. Merchant can preview, validate, dry-run, execute, and audit import without arbitrary fetch/database access or secret leakage.
4. Cutover freezes old intake and records/reconciles/partitions every still-payable legacy inventory liability regardless of key strategy.
5. A scarce-stock rehearsal with an old unpaid invoice proves that old and new systems cannot allocate the same physical unit twice.

**Plans:** 3 plans

Plans:

- [ ] 04-01: Literal NIP-15 catalog/message adapters and compatibility fixtures
- [ ] 04-02: Migration preview/import/dry-run and signed liability manifest
- [ ] 04-03: Single-writer cutover rehearsal, external client verification, and Release-C gate

## Progress

**Execution Order:** Phase 1 → Phase 2 → Phase 3 → Phase 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Conformance Profile | 3/3 | Complete    | 2026-09-20 |
| 2. Release A — Safe Web Commerce | 0/3 | Not started | - |
| 3. Release B — Gamma NIP-17 Orders | 0/3 | Not started | - |
| 4. Release C — Legacy Interop and Cutover | 0/3 | Not started | - |
