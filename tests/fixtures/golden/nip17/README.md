# Golden NIP-17 fixtures (D-08)

Checked-in golden fixtures for the section 6.9 / 8.5 gift-wrap chain. These
are normative cross-phase references — changing them after Phase 1 requires
re-qualification.

## Contents

- `keys.json` — synthetic test keypairs (sha256-derived secrets; never real
  key material).
- `rumor.json` — an unsigned kind-16 type-1 order rumor with the section 6.9
  common tags (exactly one `p`, `subject`, `type`, `order`) plus `amount`
  and `item` tags. Merchant-authored: the two-copy rule below models the
  outbound merchant rumor construction.
- `recipient/` — the buyer-addressed copy: `seal.json` (kind 13, empty tags)
  and `wrap.json` (kind 1059, one `p` tag, ephemeral outer key).
- `sender/` — the merchant-addressed sender copy, independently sealed and
  wrapped (distinct outer id and wrapper key).
- `retry/` — a retry of the recipient copy: SAME canonical rumor id with a
  fresh seal, fresh ephemeral wrapper key, and different outer event id
  (section 8.6 step 3).
- `rumor_kind14.json` — an unsigned kind-14 general-DM rumor
  (merchant -> buyer) for the section 6.9 allowlist fixture coverage.
- `rumor_kind17.json` — an unsigned kind-17 receipt rumor
  (buyer -> merchant) for the same allowlist coverage.

## Regeneration

    uv run python tests/fixtures/golden/generate_fixtures.py

Recorded seed/inputs: keys = `sha256("gammamarkets-qual:<role>")` for roles
`buyer`/`merchant`; rumor `created_at` = 1750000000; order external id =
`gq-order-01`; product d = `gq-prod-0001`.

The rumor and keys are byte-deterministic. Seals and wraps are one frozen
generation of the NIP-59 pipeline — the pinned SDK draws a fresh ephemeral
wrapper key and randomized past timestamps per copy, so regeneration
produces equivalent-but-different ciphertexts. The checked-in files are the
frozen golden reference (D-08).
