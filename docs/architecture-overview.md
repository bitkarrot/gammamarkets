# infinitemarkets — Architecture Overview (as built)

**Status:** Implementation-state document for Release A. It describes what is
actually wired today. `technical-specification.md` remains the normative
contract — where the two differ, the spec describes the target and this file
describes the current build. Items marked *Release B/C* are planned surfaces
whose schema or configuration already exists but whose behavior is not yet
implemented.

## 1. Component diagram

```
                                ┌────────────────── LNbits host ───────────────────┐
                                │                                                  │
   Browser (merchant)           │   ┌─────────────── infinitemarkets ───────────────┐ │
   ┌────────────────┐           │   │                                            │ │
   │ Admin SPA      │──session──┼──►│ Admin API  /api/v1/*                       │ │
   │ (Vue3/Quasar)  │  cookie   │   │  (check_user_exists → LNbits user)         │ │
   └────────────────┘           │   │      │                                     │ │
                                │   │      ▼                                     │ │
                                │   │   ┌──────────────────┐                     │ │
                                │   │   │ catalog.py       │ products,           │ │
                                │   │   │ merchant.py      │ collections,        │ │
                                │   │   │ themes.py        │ shipping, keys,     │ │
                                │   │   │ relay.py         │ relays, themes      │ │
                                │   │   └───────┬──────────┘                     │ │
   Browser (buyer, anon)        │   │           │                                │ │
   ┌────────────────┐           │   │           ▼                                │ │
   │ Public pages   │──GET──────┼──►│ views.py (server-rendered HTML)            │ │
   │ /p/{pk}/{d}    │           │   │  · nip89.py = public projections +         │ │
   │ /public/...    │           │   │    availability + rate limits              │ │
   │ /order#token   │           │   │  · themes.emit_css → scoped .gm-public     │ │
   └───────┬────────┘           │   │                                            │ │
           │ XHR                │   │ Public API /api/v1/public/* (no auth)      │ │
           └────────────────────┼──►│  · catalog reads (public projections only) │ │
           X-Order-Token header │   │  · POST /checkout                          │ │
                                │   │  · GET /order-status (bearer token)        │ │
                                │   │      │                                     │ │
                                │   │      ▼                                     │ │
                                │   │   checkout.py ──create_invoice──► LNbits   │ │
                                │   │   orders.py    (bolt11 via       payments  │ │
                                │   │   settlement.py wallet backend)  service   │ │
                                │   │      │                            ▲        │ │
                                │   │      ▼                            │ status │ │
                                │   │   Extension SQLite tables         │        │ │
                                │   │   (same LNbits DB file) ──────────┘        │ │
                                │   └───────┬────────────────────────────────────┘ │
                                └───────────┼──────────────────────────────────────┘
                                            │
              Background workers (tasks.py) │
              outbox_publisher     5s       │
              relay_manager        30s      │
              email_sender         5s       │
              reservation_expiry   30s      │
              reconciliation       60s      │
              retention_pruner     24h      │
                                            ▼
                        ┌─────────────────────────────────┐
                        │ outbox.py (durable intent queue)│
                        │  claim → render event from      │
                        │  CURRENT state → sign via       │
                        │  keystore → send → record ACK   │
                        └───────────────┬─────────────────┘
                                        │ send_to(urls)
                        ┌───────────────▼─────────────────┐
                        │ transport.py — owned Nostr      │
                        │ client (nostr-sdk), wss only,   │
                        │ converges to configured relays  │
                        └───────────────┬─────────────────┘
                                        │ outbound only (Release A)
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
      Merchant-configured        relay_publications table      Blossom/media
      public relays              (per-relay ACK evidence)      endpoints (config
      (wss://...)                                              only — for future
                                                               media uploads)
```

## 2. What's exposed to relays — plain English

**Outbound only, in Release A.** The extension owns its Nostr transport
(`services/transport.py`) — it does not depend on the `nostrclient` extension.
When a merchant edits catalog data, the change is saved to the extension's
tables and an *outbox intent* is queued. A background worker
(`outbox_publisher`, `services/tasks.py`) picks it up, rebuilds the event from
**current** domain state — never a stored snapshot, so retries can't publish
stale data — signs it with the merchant key (`merchant_keys` via the keystore),
sends it to the merchant's configured relays, and records each relay's
ACK/reject/timeout in `relay_publications`. That table is the evidence shown
in the Publications admin tab; relay delivery is never treated as state truth.

**What gets published:**

| Event kind | Content | When |
|---|---|---|
| `30402` | NIP-99 product listing (title, price, stock, images, specs, categories, shipping refs) | create/update, republished on changes |
| `30405` | NIP-99 collection (requires ≥1 active member by contract) | create/update |
| `30406` | Shipping option | create/update |
| `0` | Merchant profile (name, about, picture) | profile save |
| `31990` | NIP-89 handler info — tells clients this merchant serves `/p/{naddr}` product pages | publish |
| `5` | Tombstone / deletion request | product/collection/shipping delete |
| `30017` / `30018` | Literal NIP-15 stall + product | *Release C* — builders exist, not emitted yet |
| `1059` (inbound) | NIP-17 gift-wrapped buyer orders | *Release B* — `inbox_events` table and `direction=inbox` relay config exist; no subscription runs yet |

**What's never exposed:** orders, invoices, buyers' data, or internal state.
The nsec lives in `merchant_keys`, is used only for event signing, and is
never sent anywhere except the one-time TLS POST on nsec import. Blossom/media
endpoints are merchant-configurable but config-only today (no uploads yet).

## 3. How listings and orders flow within LNbits

**Catalog.** Merchant edits via the admin API → validated DTOs → extension
tables (same LNbits DB file, `infinitemarkets_*` tables) → outbox intents →
signed NIP-99 events to relays. The database is authoritative; relay events
are projections of it. Nostr clients read the relay copies; buyers read the
public pages/API, which serve public-safe projections (`nip89.py` filters out
draft, hidden, deleted, and merchant-internal fields — never raw rows).

**Orders.** Buyer checks out on the public product page → `checkout.py`
reserves inventory inside a transaction → calls LNbits `create_invoice`
(bolt11 via the configured wallet backend) → order + payment rows → 201
returns a bearer token. The order-status page keeps the token in the URL
fragment (never sent in paths or queries) and polls `/order-status` with an
`X-Order-Token` header. **Payment truth comes only from LNbits payment
state — never from relay delivery.** Background workers expire stale
reservations (releasing stock), reconcile payment status, send notification
emails, and prune retained data on fixed intervals.

**Deletion.** Soft-delete in the DB → a kind-5 tombstone is published so the
relay copy stops advertising the item — the row is kept for order and audit
history.
