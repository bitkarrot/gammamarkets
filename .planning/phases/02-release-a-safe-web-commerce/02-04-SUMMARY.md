---
phase: 02-release-a-safe-web-commerce
plan: 04
subsystem: ui
tags: [vue3, quasar, jinja-raw, checkout, order-status, admin-shell, themes]

requires:
  - phase: 02-03
    provides: §5.3 admin order/notification/outbox APIs, §5.4 public
      checkout/status/opt-out APIs, theme backend, relay-health
  - phase: 02-02
    provides: public storefront documents, theme token emission,
      relay-health/outbox routes

provides:
  - Admin shell (one nav: Orders/Catalog/Publications/Settings) mounted
    on the host Vue 3 app via mixins inside `{% block page %}`
  - B1 Linear Split order workspace (390px list + detail, legal-action
    map, exception banner, order_events timeline, collapsed technical
    details)
  - B2 publication health (per-relay delivery evidence + outbox pills +
    retry) and B3 catalog management (products/collections/shipping
    editors, draft badges, dry-run event viewer, soft-delete dialogs)
  - B4 merchant settings (identity, masked nsec import, wallet selector
    blocked on open orders, relay + Blossom editors, publish/deactivate)
    and B5 notifications (≤5 addresses, per-event toggles, test send,
    queue view) and B6 appearance (Tiered Controls + live contrast +
    public-only preview)
  - A2 embedded adaptive checkout card (Editorial/Guided/Compact,
    ≤560px compact override, persistent summary, idempotent submit) and
    A3 order-status page (fragment token → replaceState → X-Order-Token,
    5s polling, invalid-token identical copy)

affects: [release-a-verify, 03-release-b]

actuals:
  tokens: 102000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Vue mixins via window.app.mixin() — extension modules register in
      `{% block scripts %}` (after Vue.createApp, before mount)"
    - "Jinja `{% raw %}` wraps Vue `{{ }}` markup in the page block"
    - "Run-once guards on mixin mounted hooks (they fire per component)"

key-files:
  created:
    - gammamarkets/templates/gammamarkets/admin.html
    - gammamarkets/static/gammamarkets/js/admin_app.js
    - gammamarkets/static/gammamarkets/js/admin_orders.js
    - gammamarkets/static/gammamarkets/js/admin_catalog.js
    - gammamarkets/static/gammamarkets/js/admin_publications.js
    - gammamarkets/static/gammamarkets/js/admin_settings.js
    - gammamarkets/static/gammamarkets/js/admin_notifications.js
    - gammamarkets/static/gammamarkets/js/public_checkout.js
    - gammamarkets/static/gammamarkets/js/public_order.js
    - tests/runtime/test_buyer_ui.py
    - tests/runtime/test_admin_ui.py
    - tests/runtime/test_release_a_journey.py
  modified:
    - gammamarkets/views.py (index → admin.html; index.html removed)
    - gammamarkets/views_public_api.py (payment_exception on status)
    - gammamarkets/services/orders.py (list rows: buyer/item summary + q)
    - gammamarkets/services/merchant.py (spec_revision on projection)
    - gammamarkets/services/relay.py (blossom_servers on relay-health)
    - gammamarkets/templates/gammamarkets/public_product.html (A2 card)
    - gammamarkets/templates/gammamarkets/public_order.html (A3 shell)
    - gammamarkets/static/gammamarkets/css/gm-public.css (checkout/order
      styles, stepper, pills, focus/reduced-motion)
    - gammamarkets/static/gammamarkets/js/public_storefront.js (shared
      GM helpers only — checkout/status logic moved to page modules)

key-decisions:
  - "Admin JS runs as window.app mixins in `{% block scripts %}` — the
    host mounts AFTER extension scripts, so mixins land pre-mount"
  - "Public checkout/status split into page modules on a shared
    window.GM helper layer (vanilla JS, CSP script-src 'self')"
  - "Vue `{{ }}` markup lives inside `{% raw %}` in admin.html — Jinja
    would otherwise consume Vue interpolation"
  - "payment_exception added to the §5.4 status allowlist (buyer-safe
    boolean only — never the exception reason)"
  - "Verbatim contract copy kept as single-line JS constants so tests
    grep the literal strings"

requirements-completed:
  - PUB-02
  - ORD-01
  - NOTF-01
  - UI-01
  - UI-02
  - UI-03
  - WEB-01
  - WEB-02
---

# 02-04 Summary — buyer surfaces + merchant admin shell

## Tasks completed

1. **Admin shell + surfaces** — `admin.html` mounts inside the host
   shell; `admin_app.js` provides shared state/API/CSRF/navigation plus
   first-run merchant setup, topology + audit-warning banners. B1 order
   workspace (`admin_orders.js`), B2 publication health
   (`admin_publications.js`), B3 catalog (`admin_catalog.js`), B4
   merchant settings + B5 notifications + B6 appearance
   (`admin_settings.js`, `admin_notifications.js`).
2. **Buyer surfaces** — A2 adaptive checkout card embedded in
   `public_product.html` (`public_checkout.js`), A3 order-status page
   (`public_order.js`), shared token/format helpers in
   `public_storefront.js`, and the full checkout/order CSS set.
3. **Runtime UI tests + Release-A journey** — `test_buyer_ui.py` (5),
   `test_admin_ui.py` (8), `test_release_a_journey.py` (1 journey).

## Implementation notes

- **Host integration** — `window.app = Vue.createApp` precedes
  `{% block scripts %}`; `init-app.js` (in INCLUDED_COMPONENTS) mounts
  after, so extension mixins register before mount. Each module guards
  its `mounted`/`$watch` with a run-once flag — mixin hooks fire for
  every component instance.
- **B1 legal-action map** mirrors §7.1/§7.2: confirmed → Start
  processing / Cancel with reason; processing → Start fulfillment /
  Mark shipped / Mark delivered / Mark complete / Cancel;
  pre-payment states → Cancel; payment_exception → Accept / Request
  refund / Confirm refund sent; terminal → disabled "No legal action"
  with reason. Reissue revokes the old token and shows the new link once.
- **B6 theme editor** mirrors `services/themes.py` exactly — preset
  palettes, Brand Basics bounds, allowlisted advanced tokens behind the
  opt-in, client-side WCAG ≥4.5:1 meters that block save before the
  server gate runs. `validate_theme` replaces the whole object, so the
  save always sends `brand` and only sends `advanced` while opted in.
- **Token contract** — the order token arrives as a URL fragment only,
  is stripped via `history.replaceState`, lives in memory, and travels
  as `X-Order-Token`. Status links re-attach it as a fragment only when
  the user explicitly copies the link.
- **Invoice states** — creating skeleton → awaiting_payment (QR + full
  BOLT11 + countdown + verbatim security copy) → confirmed/processing/
  completed → expired/cancelled; `creation_unknown`/`payment_exception`
  render the on-hold hold state with NO second-invoice affordance.

## Fixes found by tests

- `relay_health` lacked `blossom_servers` — added so B2/B4 share one
  response shape.
- `list_orders` lacked buyer/item summary fields — extended (decrypted
  buyer handle post-filter for the `q` search arm).
- `outbox_events` has no `relay_targets` column — `gmMissingRelays`
  derives partial-publication gaps from configured enabled public relays
  minus accepted `relay_publications`.
- `payment_exception` added to `GET /public/order-status` (plan
  allowlist) — the strict field-set test now names it explicitly.
- `index.html` removed — `admin.html` is the admin surface.
- 02-02 test updated: the A2 CTA is "Review payment" (UI-SPEC), not the
  placeholder "Buy with Lightning".

## Spec deltas (recorded per plan)

- **`payment_exception` on §5.4 order-status** — buyer-safe boolean for
  the "On hold — the merchant is reviewing a payment issue." label.
- **B4 relay/blossom editing** uses `PATCH /merchants/{id}` with
  `relay_configs`/`blossom_servers` — the config fields land in the
  merchant document, not a separate route (W-NEW-1 precedent).

## Verification

```
uv run ruff check .                    → all checks passed
node --check on all 9 JS modules       → clean
uv run pytest tests/runtime -q         → 171 passed
GAMMA_QUAL_EVIDENCE=1 uv run pytest -q → 391 passed, 1 skipped
```

Runtime coverage: `test_buyer_ui` (checkout card contract, physical vs
digital field sets, order-page shell, JS contracts — ≤560px override,
idempotency key, creation_unknown guard, verbatim copy, scoped theme
emission), `test_admin_ui` (shell mount, verbatim copy, workspace grid
CSS, no-secrets boundaries, legal-action map, B2/B5/B6 module checks),
`test_release_a_journey` (full merchant+buyer pass: catalog → page →
checkout → replay → status → settle → admin action → publications →
notifications → appearance → themed page).

Not verified: real browser rendering (Playwright E2E follows as a
separate task); PostgreSQL `SKIP LOCKED` variants (CI).
