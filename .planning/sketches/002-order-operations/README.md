---
sketch: 002
name: order-operations
question: "How should merchants triage, inspect, and act on paid, pending, cancelled, and exception orders?"
winner: "A"
tags: [admin, orders, list-detail, timeline]
---

# Sketch 002: Order Operations

## Design Question

How should merchants triage, inspect, and act on paid, pending, cancelled, and exception orders?

## How to View

Open `.planning/sketches/002-order-operations/index.html` or use the running local sketch server.

## Variants

- **A: Linear Split — selected** — Compact order list and persistent detail pane optimize rapid keyboard-like triage.
- **B: Queue Board** — Status-oriented queues and a contextual drawer make workload distribution immediately visible.
- **C: Timeline Focus** — A restrained queue rail gives most space to payment, inventory, fulfillment, and audit chronology.

## Decision

Use the Linear-style split list/detail workspace as the primary merchant order surface. Preserve the board as an optional overview pattern and the full timeline inside the selected order detail rather than as the default navigation model.

## What to Look For

- Scan speed and exception visibility
- Confidence before state-changing actions
- Whether payment, inventory, and shipping state remain distinguishable
- Timeline readability
- Technical detail disclosure without overwhelming routine work
- Mobile and tablet viability
