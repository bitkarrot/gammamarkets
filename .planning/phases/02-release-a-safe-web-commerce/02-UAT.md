---
status: testing
phase: 02-release-a-safe-web-commerce
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
  - 02-03-SUMMARY.md
  - 02-04-SUMMARY.md
started: 2026-09-27T07:17:00Z
updated: 2026-09-27T07:36:11Z
---

## Current Test

number: 1
name: Buyer price and checkout clarity
expected: |
  On the fresh 5099 storefront, editing quantity and physical delivery refreshes the Items, Shipping and Total amounts before payment can be submitted. The created invoice matches that total; uncertain payment state never offers Pay Again.
awaiting: user response

## Tests

### 1. Buyer price and checkout clarity
expected: The updated storefront shows a correct, readable server-priced quote and invoice amount. Shipping and quantity changes update the total; unavailable quotes do not initiate a payment. Retry/error messages do not invite a second payment.
result: pending

### 2. Order link and merchant operations
expected: Opening a private order link removes the URL fragment immediately; the status remains private. The merchant sees that order in a split list/detail workspace, including lawful actions, audit chronology and publication evidence without buyer secrets.
result: pending

### 3. Responsive storefront and appearance
expected: Editorial, Guided and Compact remain visually distinct, mobile checkout remains usable, a multi-image product has accessible gallery controls where the layout shows thumbnails, and each theme has readable text, focus and button states. Admin chrome is unaffected by a merchant's public theme.
result: pending

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

Machine evidence is separate: 13 Chromium tests passed against each isolated SQLite and PostgreSQL server; seven Chromium smoke tests passed on the fresh port 5099 demo without creating or settling an order, and its quote route returned HTTP 200 with a 2,500-sat total. Neither those tests nor earlier demo screenshots count as a new human response to the tests above. The user-requested 5099 replacement runs current code on a fresh disposable database; the prior demo's database files were left untouched but are not mounted in this demo.

## Gaps

None reported by the user in this UAT session. Unanswered tests are pending, not passes or failures.
