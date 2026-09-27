---
name: ecommerce-design-guide
description: Conversion-focused ecommerce design rules (visual layer, shared design patterns, usability/UX, mobile, accessibility, merchant-operable storefronts) distilled from Charle Agency's "Best Ecommerce Web Designs" guide. Use when designing, reviewing or restyling gammamarkets storefront, product, checkout, order-status or merchant admin surfaces.
---

<context>
Source: Nic Dunn, "The Best Ecommerce Web Designs, and the Decisions Behind Them", Charle Agency (updated July 28, 2026) — https://www.charleagency.com/articles/best-ecommerce-web-designs

Core framing: every design decision either **reduces the effort required to buy** (craft: fast pages, sane navigation, filters that match how people shop, checkout without a password) or **increases the reason to buy from this shop** (brand: photography, typography, tone, a real business with a point of view). Stores that only reduce effort look like templates; stores that only add reason win awards and lose money. Do both.

Use together with `sketch-findings-gammamarkets` (the locked gammamarkets visual contract). Where they conflict, the normative spec, security and payment invariants win, then the sketch contract, then this guide.
</context>

<visual_layer>
## The Visual Layer — last to design, first to be judged

Build it on decisions already made about who buys and how they shop.

- **Photography is infrastructure, not a shoot.** Treat product images as a repeatable system: fixed crop and aspect ratio, consistent background, at least one scale reference, at least one in-use image. Weak photography cannot be rescued by layout. In gammamarkets: fixed aspect-ratio frames for cards and galleries, graceful placeholder when a product has no image, never let images shift layout.
- **Typography carries the brand when photography cannot.** Pick a pairing early: one expressive display voice, one workhorse UI face; test both at the small sizes where most reading happens (13px spec tables, checkout labels). Rules: body ≥16px on mobile, line length ≈70ch, paragraph line-height ≈1.5, contrast ≥4.5:1.
- **Branding = consistency across every template**, including the ones nobody designs: search/empty results, empty collection, sold-out state, order confirmation, invalid link, expired invoice, emails. These are where stores revert to defaults and lose the thread.
- Minimal gallery-led layouts suit considered purchases; denser editorial layouts suit community/content value. The right style is testable, not taste.
</visual_layer>

<design_patterns>
## The Design Patterns Every High Performer Shares

1. **State shipping cost before checkout.** Unexpected costs are the #1 abandonment reason (48%). Answer shipping (and tax/currency) on the product/category page or a persistent bar, not three steps in.
2. **Photography as infrastructure** (above).
3. **Navigation shaped by demand, not the org chart.** Categories/collections named the way shoppers search. Top-level nav must exist on every page; the shopper can always get back to the shop.
4. **Social proof at the moment of doubt** — near price for comparers, on cards for scanners. (gammamarkets: reviews are V2-04; use honest trust signals instead: stock, delivery method, payment privacy.)
5. **Variants as swatches/chips, never a bare dropdown.**
6. **Checkout asks for as little as possible.** Forced account creation is the #2 abandonment reason (26%), complicated checkout #3 (22%). Guest checkout and a single-page flow are table stakes — gammamarkets' no-account private-link checkout is aligned with this; keep it.
7. **Everything is measured** — prefer A/B evidence over opinion.
8. **SEO and design are one project** — heading structure, internal links between collections and products, image alt text, stable templates.
</design_patterns>

<usability>
## Usability and the UX Details That Decide Sales

- UX is the absence of a hundred small frictions. Common failures: search that fails on plurals/misspellings, filters that reset on back, drawers that dump users to the top, size guides that break on mobile, **sold-out variants with no next step**.
- **Design the states nobody designs**: a collection with three products, a promotion ending mid-session, a declined/expired payment, an uncertain payment, a lost order link, a closed order. Every state needs a clear message and a next action.
- **Usability testing beats opinion**: five people doing a real task ("buy the poster and ship it to Illinois", "find your order again") reveal the backlog; hesitations are bugs.
- Check analytics for zero-result searches, high-traffic/low-add-to-cart pages, and the exact checkout step where sessions end.
- Status must never rely on color alone — pair color with a label or icon (also an accessibility rule).
</usability>

<mobile_speed_a11y>
## Mobile, speed and accessibility

- **Mobile is the design, not a version of it.** Design 390px first; whatever survives is what matters. Keep the primary buy/pay control reachable (sticky or immediately visible); forms must cooperate with the on-screen keyboard (correct `inputmode`/`autocomplete`); show cost early; nav must be thumb-operable, not a wall of links.
- **Speed is a design constraint**: LCP < 2.5s, INP < 200ms, CLS < 0.1. Reserve space for images, lazy-load below the fold, cap third-party scripts (gammamarkets: none allowed on public pages), prefer native features.
- **Accessibility (WCAG 2.1 AA)**: text contrast ≥4.5:1, visible focus on every control, persistent labels (not placeholder-only), meaningful alt text, errors communicated with text/icon not just a red border.
</mobile_speed_a11y>

<shopify_lesson>
## The Shopify lesson — merchant-operable design

Shopify's advantage (Horizon theme blocks, nested group blocks) is that **merchandisers can restructure and update pages without a developer**. "A beautiful build that requires a developer for a homepage banner change will be worked around within a quarter, and the workarounds are what visitors see." Judge a storefront system by the customization the shop owner can perform without a deployment.

Applied to gammamarkets:
- Storefront content that changes often (announcement/shipping message, hero tagline, featured collections, theme, layout preset) must be editable from the merchant admin, bounded and validated (no arbitrary CSS/HTML/scripts — see theme guardrails).
- The owner must reach the live storefront in one click from the admin's top-level navigation.
- Admin copy is for shop owners, not engineers: no state-machine jargon ("legal action"), plain verbs and outcomes.
</shopify_lesson>

<checklist>
## Review checklist

- [ ] Every public page has top-level navigation back to the shop, its collections, and order tracking; plus a footer.
- [ ] Price, shipping (or "digital — no shipping"), and delivery method visible before checkout.
- [ ] Every state (empty, sold out, expired, uncertain, closed, lost link, error) has a message and a next step.
- [ ] Status colors are semantic, distinct, and paired with text.
- [ ] Mobile 390px: primary action reachable, forms keyboard-friendly, nav thumb-operable.
- [ ] Contrast ≥4.5:1, visible focus, persistent labels, alt text.
- [ ] No layout shift from images; no third-party scripts.
- [ ] Merchant can change frequently edited storefront content without code; storefront is one click from the admin.
- [ ] Admin copy uses plain language a shop owner understands.
</checklist>
