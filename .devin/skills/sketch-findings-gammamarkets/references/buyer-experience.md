# Buyer Experience & Responsive Checkout

## Design Decisions

- Preserve three merchant-selectable public layout presets:
  - **Editorial** — rich product display and product context;
  - **Guided** — explicit Product, Delivery, and Pay progression;
  - **Compact** — progressive disclosure optimized for narrow screens.
- Use adaptive overrides rather than obeying a preset blindly. Mobile falls back to Compact; desktop can combine Editorial display with Guided checkout.
- Buyers do not choose the checkout layout. The merchant chooses a bounded preference; gammamarkets applies responsive safety.
- Keep the full payable total visible before invoice creation in every preset.
- Keep product, shipping, email consent, invoice, confirmed, and expired states behaviorally identical across presets.
- Invoice state shows QR, copy action, amount, expiry, waiting state, and recovery. Payment confirmation comes only from LNbits.
- Order tokens remain in memory/header flow and never appear in paths or query strings.

## CSS Patterns

```css
.product-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: clamp(28px, 5vw, 72px);
}

.checkout-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

.preview-mobile .product-layout {
  grid-template-columns: 1fr;
}
```

Use 44px minimum interactive targets, visible `:focus-visible`, inline errors, and `prefers-reduced-motion` handling.

## HTML Structures

```html
<div class="progress" aria-label="Checkout progress">
  <div class="progress-step active">1 Product</div>
  <div class="progress-step">2 Delivery</div>
  <div class="progress-step">3 Pay</div>
</div>

<div class="summary">
  <div class="summary-line">Items <strong>48,000 sats</strong></div>
  <div class="summary-line">Shipping <strong>3,500 sats</strong></div>
  <div class="summary-line total">Total <strong>51,500 sats</strong></div>
</div>
```

## Required States

- Product available, sold, hidden, and invalid variation
- Validation error and consent missing
- Invoice creating, waiting, confirmed, expired, and creation uncertain
- Order confirmed, cancelled, and payment exception
- Loading, no-route, relay delivery delayed, and email suppressed/failed where surfaced

## What to Avoid

- Letting themes or layout presets hide totals or reorder security-critical fields
- Buyer-facing layout choosers
- Spinner-only payment feedback
- Automatically creating another invoice after uncertainty
- Desktop layouts squeezed into mobile instead of adapting
- Third-party scripts, trackers, remote fonts, or arbitrary merchant CSS

## Origin

Synthesized from sketch 001. Full source: `sources/001-buyer-checkout/`.
