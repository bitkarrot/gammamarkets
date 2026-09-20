# UI/UX Research Notes

## Source

The user-provided research is an eight-page Chromium/Skia PDF created on 2026-09-20 and copied to `research/best-simple-shopping-admin-ui.pdf` for project-local reference.

## Strongest Findings

- Public storefront and internal administration should share primitives and tokens but differ in density and hierarchy.
- Apple- and Shopify-style customer surfaces emphasize visual hierarchy, early totals, persistent summaries, explicit payment actions, and field-specific recovery.
- Linear-, Stripe-, and Vercel-like operator surfaces emphasize compact lists, filters, structured detail, chronological history, activity, and logs.
- Operational queues, search, state, receipts, and audit history should precede dashboard charts.
- Theme customization should operate through bounded tokens—color, type, radius, spacing, and surfaces—not arbitrary CSS scattered across features.

## Evidence Caveat

Baymard-backed checkout guidance is stronger than the secondary design blogs and Perplexity links in the source. The named products are comparative inspiration, not a gammamarkets contract. Checkout field-count guidance is an optimization target rather than a hard limit, particularly for physical shipping.

## LNbits Adaptation

LNbits supplies Vue 3 and Quasar through its base template. gammamarkets should use shared Quasar-compatible shapes and CSS variables instead of adding React, Tailwind, or shadcn solely for aesthetics. The existing `nostrmarket` extension remains useful as a functional and data reference, but its wide tab strip and component coupling are not the information-architecture template.

## Page Inventory

### Public

- Catalog
- Product detail
- Checkout
- Lightning invoice/payment state
- Order status

### Merchant

- Overview
- Catalog
- Orders
- Publications
- Relay health
- Notifications
- Settings
- Migration

## Timing

Explore low-fidelity interactive sketches now. Produce a binding Phase 2 UI contract only after the conformance phase passes, before Release A implementation planning.
