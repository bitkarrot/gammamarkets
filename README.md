# Infinitemarkets

An [LNbits](https://github.com/lnbits/lnbits) extension that gives a merchant one authoritative inventory across two storefronts: a classic web shop with Lightning checkout, and a native Nostr/Gamma commerce channel with encrypted (NIP-17) ordering.

**One inventory, two rails.** Web and Nostr orders flow through the same pricing, reservation, invoice, and settlement pipeline — no duplicate invoices, no double allocation, and relay delivery is never mistaken for payment truth.

## Features

### Catalog & web commerce (Release A)
- Products, collections, shipping options, and visibility flags (`on-sale`, `hidden`, `pre-order`, draft)
- Public storefront with private per-order links — no buyer accounts required
- Lightning checkout: quote → reservation → invoice → settlement saga with late-settlement reconciliation
- Reversible order archiving, bulk catalog operations, order notifications over host SMTP
- NIP-99 catalog publication to public relays with durable per-relay outbox evidence

### Gamma Nostr orders (Release B)
- **Kind-10050 inbox profile**: merchants publish declared inbox relays and activate only after reachability is proven
- **NIP-17 encrypted ordering**: kind-16 order/payment/status messages and kind-17 receipts over gift-wrapped (kind-1059) transport
- **Dual-copy protocol**: independent sender and recipient copies routed only to each party's declared relays
- **Durable inbox**: verified/deduplicated outer-seal-rumor identity, encrypted history, resumable cursors, overload shedding before decrypt
- **NIP-42 relay authentication** and paid-relay support (`payment-required` surfaces the invoice for external payment — the extension never spends)
- **NIP-07 sign-in** for buyers: order history, retroactive order claiming via private links, token-equivalent access to digital delivery
- **Storefront modes**: `full`, `showcase`, `browse_only`, `nostr_only` — private order links and in-flight invoices keep working in every mode
- **Admin Messages workspace**: customer/unknown folders, unread markers, thread reply/compose, per-relay delivery evidence, retry, rejected-intake review with mute

## Requirements

- LNbits ≥ **1.6.0** (developed and conformance-tested against `v1.6.2-rc1`, host pin `e336fe14`)
- Python extension support enabled on the host (standard LNbits extension loader)
- A bound merchant wallet (Lightning funding source) for invoice creation
- For Nostr flows: outbound websocket access to buyer/merchant declared relays; a recipient-gated relay (e.g. the LNbits `nostrrelay` extension) is the reference inbox deployment but is **not** a runtime dependency

## Installation

### Remote install (extension manifest)

Add the release manifest URL to the host's extension sources — LNbits admin UI → **Server → Extensions → Manifest sources**, or the `LNBITS_EXTENSIONS_MANIFESTS` setting:

```
https://github.com/bitkarrot/infinitemarkets/releases/download/v0.1.0/manifest.json
```

The extension then appears in the extension manager and installs with sha256 verification against the release archive. The zip layout follows the LNbits contract: a single top-level `infinitemarkets/` directory containing `config.json` and the package.

> Note: the manifest embeds the sha256 of the release zip — per-release manifests are attached to each GitHub release. Do not point at a manifest for a different version than you intend to install.

### Local / development install

```bash
git clone https://github.com/bitkarrot/infinitemarkets.git
cd infinitemarkets
make host        # checks out the pinned LNbits host into .cache/lnbits
```

Symlink or copy `infinitemarkets/` into the host's extensions directory, or run the harness/e2e tooling which boots a disposable host (see `tools/e2e_server.py`).

## Configuration

All extension settings use the `INFINITEMARKETS_` prefix. The extension refuses to start without the three required secrets:

| Variable | Required | Purpose |
|---|---|---|
| `INFINITEMARKETS_MASTER_KEYS` | yes | JSON map `{"v1": "<base64 32B>", ...}` — keyring for sensitive-field encryption |
| `INFINITEMARKETS_ACTIVE_KEY_VERSION` | yes | Active key id; must exist in the keyring |
| `INFINITEMARKETS_PRIVACY_KEY` | yes | Independent privacy/encryption key (must differ from master keys) |
| `INFINITEMARKETS_PUBLIC_BASE_URL` | yes | `https://` origin used in buyer-facing links (no path/userinfo) |
| `INFINITEMARKETS_RESERVATION_TTL` | | Inventory hold seconds (default `900`) |
| `INFINITEMARKETS_OUTBOX_MAX_ATTEMPTS` / `_BATCH` | | Relay publish retry bound / batch size |
| `INFINITEMARKETS_PEER_RELAY_TTL` | | Discovered peer-relay record TTL (default `86400`) |
| `INFINITEMARKETS_INBOX_MAX_EVENT_BYTES` / `_AUTHOR_CAP` | | Inbound size cap / per-author admission cap |
| `INFINITEMARKETS_CHECKOUT_RATE_LIMIT` / `_HOURLY` | | Buyer checkout rate limits |
| `INFINITEMARKETS_EMAIL_ENABLED` / `_MAX_ATTEMPTS` | | Order notification email |

Generate keys e.g. `openssl rand -base64 32`.

## Storefront modes

| Mode | Web browse | Web checkout | Nostr listings | Nostr orders |
|---|---|---|---|---|
| `full` (default) | ✓ | ✓ | ✓ | ✓ |
| `showcase` | ✓ | guided "Order via Nostr" | ✓ | ✓ |
| `browse_only` | ✓ | — | paused | — |
| `nostr_only` | notice only | — | ✓ | ✓ |

Switching to `showcase`/`nostr_only` requires proven Nostr inbox readiness. Existing private order links, in-flight invoices, and sign-in work in every mode.

## Security posture

- Relay-target egress screening: discovered/inbox relay targets are DNS-resolved and non-global ranges (private, loopback, link-local, multicast, reserved, metadata incl. `169.254.169.254`, CGNAT) rejected at validate, connect, and reconnect — IPv4 and IPv6
- The extension **never** invokes outgoing-payment APIs — paid-relay invoices are surfaced for external payment only
- Encrypted at rest: NIP-17 payloads and buyer identifiers are stored encrypted; rejected intake is auditable
- OS/container egress policy remains an operator responsibility when claiming Release-B conformance (see `PINS.md` §8 and spec decision 30)

## Conformance status

Release-B evidence is reproducible: the scripted conformance matrix (`tests/conformance/run_matrix.sh matrix`) runs a real recipient-gated `nostrrelay` environment, egress/NIP-42/paid-write/overload drills, and an independent external-client matrix against a pinned `PlebeianApp/market` clone — 14/14 probes with a recorded 6-entry known-delta register (`evidence/conformance/`).

**Outstanding manual gate**: the live `plebeian.market` public-relay smoke is a manual checklist (`tests/conformance/README.md`) recorded as pending in `.planning/phases/03-release-b-gamma-nip-17-orders/03-VERIFICATION.md`.

## Development

```bash
make verify          # full suite + durable evidence (SQLite or Postgres per env)
make verify-runtime  # extension runtime tests only
make verify-fast     # fast subset
make lint            # ruff
make package         # build dist/infinitemarkets-<v>.zip + dist/manifest.json
```

- Node **22 or 24** required for the Playwright suite (`tests/e2e/`) — enforced by `.nvmrc` and engines
- Use an isolated `LNBITS_DATA_FOLDER` for parallel test runs; the shared `.cache/qual-data/` database is not safe for concurrent use
- Pinned host/SDK/tooling: `PINS.md`. Normative protocol contract: `docs/technical-specification.md`

## Repository layout

```
infinitemarkets/        # the extension package (installed unit)
  services/             # commerce, relay, inbox, outbox, auth services
  static/  templates/   # Quasar/Vue admin + public surfaces
docs/                   # technical specification
tests/                  # qualification, runtime, e2e, conformance suites
tools/  harness/        # host checkout, e2e server, test harness
evidence/               # conformance + qualification evidence bundles
.planning/              # GSD project plans, decisions, verification records
```

## License

See repository owner for licensing.
