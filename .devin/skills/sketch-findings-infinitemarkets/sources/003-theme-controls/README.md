---
sketch: 003
name: theme-controls
question: "How much storefront customization can be offered without destabilizing checkout or admin usability?"
winner: "D"
tags: [themes, tokens, settings, preview]
---

# Sketch 003: Theme Controls

## Design Question

How much storefront customization can be offered without destabilizing checkout or admin usability?

## How to View

Open `.planning/sketches/003-theme-controls/index.html` or use the running local sketch server.

## Variants

- **A: Presets Only** — Merchants select Warm Market, Clean Minimal, or High Contrast with no token editing.
- **B: Brand Basics** — Presets plus bounded logo, accent, type, and corner controls with live contrast feedback.
- **C: Advanced Tokens** — A guarded token editor exposes more color, density, and shape controls while still forbidding arbitrary CSS.
- **D: Tiered Controls — selected** — Presets are the default; Brand Basics and Advanced Tokens are progressive opt-ins with the same contrast and structural guardrails.

## Decision

Use tiered controls in v1. Start every merchant on one of three tested presets, expose bounded brand identity next, and place advanced tokens behind an explicit opt-in. Merchant customization affects public surfaces only; admin styling, checkout structure, totals, validation, and payment states remain fixed.

## What to Look For

- Whether customization feels useful without becoming a design tool
- Ability to preserve checkout readability and contrast
- Clarity that merchant branding affects public pages, not the operational admin plane
- Reversibility and preview confidence
- Complexity appropriate for v1
