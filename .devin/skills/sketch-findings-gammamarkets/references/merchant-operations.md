# Merchant Operations & Audit

## Design Decisions

- Primary order surface is a compact split workspace: searchable/filterable list on the left and persistent detail on the right.
- Use a single page for rapid triage; preserve selection while filters or statuses update.
- Distinguish order, payment, inventory, shipping, publication, and relay state. Do not compress them into one ambiguous status.
- Show exceptions above routine detail with an explicit explanation and only legal actions.
- Keep payment/inventory/fulfillment chronology inside the order detail pane. Timeline-first navigation is secondary, not the default.
- A queue board can appear as an overview, but daily action uses the split workspace.
- Technical relay and correlation evidence stays behind progressive disclosure and never exposes private keys, complete BOLT11 values, payment hashes, or bearer tokens.
- On mobile, selection navigates from list to a full detail surface with an explicit Back to orders action.

## CSS Patterns

```css
.workspace {
  display: grid;
  grid-template-columns: 390px minmax(0, 1fr);
}

.order-row.active {
  background: color-mix(in srgb, var(--color-primary) 10%, var(--color-surface));
  box-shadow: inset 3px 0 var(--color-primary);
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(240px, 0.6fr);
}
```

## HTML Structures

```html
<button class="order-row active">
  <div>
    <strong>NRG-1042</strong>
    <span class="protocol">Web</span>
    <div>buyer@example.com · Hand-thrown Nostr Mug</div>
  </div>
  <div>
    <strong>51,500 sats</strong>
    <span class="status confirmed">Confirmed</span>
  </div>
</button>
```

Order detail should contain:

1. reference/channel/buyer summary;
2. exception banner when applicable;
3. legal contextual actions;
4. total/payment/inventory/protocol metrics;
5. item and fulfillment data;
6. chronological order events;
7. collapsed technical delivery evidence.

## What to Avoid

- Wide top-tab navigation copied from `nostrmarket`
- Dashboards led by vanity charts instead of actionable queues
- State-changing icon-only buttons without labels or reasons
- Treating relay delivery or buyer receipts as payment settlement
- Hiding late-payment/cancellation conflicts inside logs
- Applying storefront branding to operational admin screens

## Origin

Synthesized from sketch 002. Full source: `sources/002-order-operations/`.
