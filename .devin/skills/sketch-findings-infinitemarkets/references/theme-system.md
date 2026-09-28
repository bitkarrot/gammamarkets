# Theme System & Guardrails

## Design Decisions

Use tiered storefront customization:

1. **Preset** — default mode; select Warm Market, Clean Minimal, or High Contrast.
2. **Brand Basics** — store name/logo initials, primary accent, approved type style, and corner character.
3. **Advanced Tokens** — explicit opt-in for bounded background, surface, text, spacing, radius, and related safe tokens.

Every tier is reversible and previewed. Advanced save is blocked when text/background or primary/button contrast fails WCAG AA.

Customization applies only to public surfaces. Admin density, navigation, status colors, and action hierarchy remain LNbits-consistent. Themes cannot inject arbitrary CSS, scripts, fonts, markup, or URLs.

## Core Presets

### Warm Market

- Background `#f7f1e8`
- Surface `#fffaf3`
- Text `#2b241f`
- Primary `#a34f2a`
- Accent `#d69a3a`
- Rounded, warm independent-shop character

### Clean Minimal

- Background `#f4f7f7`
- Surface `#ffffff`
- Text `#172223`
- Primary `#266760`
- Neutral product-forward character

### High Contrast

- Background `#0b0f14`
- Surface `#141a21`
- Text `#f7fafc`
- Primary `#ffb000`
- Low-light and high-contrast character

## CSS Pattern

```css
:root {
  --color-bg: #f7f1e8;
  --color-surface: #fffaf3;
  --color-border: #dfcfbb;
  --color-text: #2b241f;
  --color-primary: #a34f2a;
  --color-on-primary: #ffffff;
  --radius-md: 10px;
  --radius-lg: 16px;
}
```

Implementation should map stored theme settings to a validated allowlisted token object. Never persist or render free-form CSS.

## Save Gates

- Text/background contrast at least 4.5:1 for normal text
- Primary/on-primary contrast at least 4.5:1
- Visible focus token remains valid
- Semantic success/warning/danger/info colors remain system-controlled
- Checkout structure and total visibility are immutable
- Responsive fallback always wins over merchant preference

## What to Avoid

- Arbitrary CSS or remote stylesheets
- Merchant-controlled admin themes
- Theme controls that change payment or validation semantics
- Unlimited font selection or remote font loading
- Color controls without live preview and contrast feedback
- Advanced controls as the default experience

## Origin

Synthesized from sketch 003. Full source: `sources/003-theme-controls/` and `sources/themes/`.
