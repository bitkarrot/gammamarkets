---
sketch: 001
name: buyer-checkout
question: "How should product selection, shipping, Lightning invoice, and payment status balance speed with confidence?"
winner: "D"
tags: [buyer, checkout, lightning, responsive]
---

# Sketch 001: Buyer Checkout

## Design Question

How should product selection, shipping, Lightning invoice, and payment status balance speed with confidence?

## How to View

Open `.planning/sketches/001-buyer-checkout/index.html` or serve the repository with a local static server.

## Variants

- **A: Split Confidence** — Spacious product gallery and sticky checkout card keep product context and the complete payable total together.
- **B: Guided Steps** — Product, delivery, and payment are separate steps while a persistent order summary keeps the total visible.
- **C: Express Sheet** — A compact single-surface flow uses progressive disclosure for shipping and detail while preserving the total before payment.
- **D: Adaptive Blend — selected** — Merchants choose Editorial, Guided, or Compact as a bounded preset; desktop combines A's product display with B's explicit stages, while mobile safely falls back to C's compact flow. Checkout fields, totals, and security semantics stay fixed.

## Decision

Preserve A/B/C as merchant-selectable layout presets with responsive overrides. Do not make buyers choose a checkout UI, and do not let presets alter validation, totals, payment creation, or order-state behavior.

## What to Look For

- Completion speed
- Total visibility
- Confidence before invoice creation
- Mobile usability
- Recovery from invalid or expired state
- How well independent-merchant warmth survives without checkout clutter
