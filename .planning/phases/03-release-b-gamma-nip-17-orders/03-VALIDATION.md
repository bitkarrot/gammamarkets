---
phase: "03"
slug: "release-b-gamma-nip-17-orders"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-27"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (uv-locked env) + Playwright/Chromium (Node 22 or 24 only) |
| **Config file** | `pyproject.toml`, `Makefile`, `tests/e2e/playwright.config.ts` |
| **Quick run command** | `make verify-fast` |
| **Full suite command** | `make verify-runtime` (SQLite + PostgreSQL) + Node 22 Playwright suite |
| **Estimated runtime** | ~90–300 seconds |

---

## Sampling Rate

- **After every task commit:** Run `make verify-fast`
- **After every plan wave:** Run `make verify-runtime`
- **Before `/gsd-verify-work`:** Full suite must be green (SQLite + PostgreSQL + browser)
- **Max feedback latency:** 300 seconds

---

## Per-Task Verification Map

*Seeded at planning time; task rows are populated by validate-phase once PLAN.md files exist.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | GAM-01..GAM-05 | TBD by planner threat models | see 03-RESEARCH.md §Validation Architecture | — | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/runtime/test_nip17_inbox.py` — durable inbox processing (dedup, cursors, crash recovery)
- [ ] `tests/runtime/test_nip17_outbox.py` — dual-copy order_msg publication evidence
- [ ] `tests/runtime/test_nostr_signin.py` — NIP-07 challenge/session, order list, claiming
- [ ] `tests/runtime/test_storefront_modes.py` — four-mode gating invariants
- [ ] `tests/runtime/test_intake_abuse.py` — rejected intake, mute, per-author caps
- [ ] `tests/e2e/` additions — Messages surface, shop-mode panel, sign-in flows

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live plebeian.market smoke run | GAM-05 | External live instance; pinned-clone matrix is scripted | Documented smoke checklist in conformance report |
| Public-relay conformance run | GAM-05 | Real-world relay behavior non-deterministic | Documented run recorded into phase verification |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 300s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
