# Golden NIP-89 fixtures (D-08)

Checked-in golden fixtures for the section 6.5 application-handler pair and
the section 5.4 naddr handler.

## Contents

- `handler_31990.json` — kind 31990 handler information; `d` =
  `gqapp-rec-001` (the merchant's `recommended_app_d`), `k` tag = `30402`,
  `web` tag carrying the `<bech32>` placeholder pattern.
- `recommendation_31989.json` — kind 31989 recommendation; `d` = `"30402"`
  (the supported event KIND, not the app id — section 6.5; the pair's
  intentionally different `d` values are caught by these fixtures),
  `a` tag -> `31990:<merchant_pubkey>:gqapp-rec-001` with a relay hint and
  `web` platform marker.
- `naddr.txt` — a valid bech32 `naddr` for `30402:<merchant_pubkey>:gq-prod-0001`
  carrying a `wss://relay.example.com` relay hint (hints are recorded but
  never fetched — section 5.4).

## Regeneration

    uv run python tests/fixtures/golden/generate_fixtures.py

Recorded seed/inputs: merchant key = `sha256("gammamarkets-qual:merchant")`;
`recommended_app_d` = `gqapp-rec-001`; product d = `gq-prod-0001`. Event ids
and the naddr bech32 are fully deterministic; signatures are one frozen
generation (schnorr aux randomness is drawn per signing).
