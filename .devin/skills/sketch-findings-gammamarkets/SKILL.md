---
name: sketch-findings-gammamarkets
description: Validated gammamarkets UI decisions, responsive checkout patterns, merchant order operations, and guarded theme controls. Use during Phase 2 UI specification, planning, implementation, or review.
---

<context>
## Project: gammamarkets

The visual direction is a warm independent-shop storefront with Shopify-clear checkout and a compact Linear-like merchant control plane. Public pages are spacious and confidence-building; admin surfaces are dense and operational. The implementation must remain compatible with LNbits Vue 3 and Quasar conventions.

Reference points: Shopify checkout clarity, Linear list/detail efficiency, Stripe chronology, Vercel activity/log disclosure, and the LNbits host shell.

Sketch session wrapped: 2026-09-20.
</context>

<usage>
## When to Load

Load this skill before:

- `/gsd-ui-phase 2` or equivalent Phase 2 UI contract authoring;
- planning or implementing storefront, checkout, payment, order-status, admin order, or theme settings surfaces;
- reviewing UI changes for responsive, accessibility, state, or design-direction drift.

Read the normative contract first. These findings define presentation and interaction; they never override payment, security, state-machine, routing, or privacy requirements.
</usage>

<design_direction>
## Overall Direction

- Default public mood: Warm Market—friendly, independent, trustworthy, and restrained.
- Buyer flow: merchant-selectable Editorial, Guided, or Compact layout presets with safe responsive overrides. Mobile uses compact behavior; checkout semantics remain invariant.
- Admin flow: Linear-style split list/detail order workspace with exception prominence and the complete audit timeline inside the detail pane.
- Theme flow: three tested presets first, bounded Brand Basics second, and guarded Advanced Tokens as an explicit opt-in.
- Public theme choices never style the admin control plane or change checkout fields, totals, validation, payment states, focus visibility, or security copy.
- Use Vue/Quasar-compatible primitives and CSS custom properties; do not introduce React, Tailwind, or shadcn solely for aesthetics.
</design_direction>

<findings_index>
## Design Areas

| Area | Reference | Key Decision |
|------|-----------|--------------|
| Buyer Experience & Responsive Checkout | `references/buyer-experience.md` | Preserve Editorial/Guided/Compact presets; use adaptive responsive fallback with invariant checkout semantics |
| Merchant Operations & Audit | `references/merchant-operations.md` | Use a compact split list/detail workspace with embedded timeline and explicit exception actions |
| Theme System & Guardrails | `references/theme-system.md` | Use tiered controls: tested presets, bounded brand basics, guarded advanced tokens |

## Themes

Theme sources are in `sources/themes/`:

- `default.css` — Warm Market
- `clean-minimal.css` — Clean Minimal
- `high-contrast.css` — High Contrast

## Source Files

The full interactive sketches and README decisions are preserved under `sources/001-buyer-checkout/`, `sources/002-order-operations/`, and `sources/003-theme-controls/`.
</findings_index>

<metadata>
## Processed Sketches

- 001-buyer-checkout — winner D, Adaptive Blend
- 002-order-operations — winner A, Linear Split
- 003-theme-controls — winner D, Tiered Controls
</metadata>
