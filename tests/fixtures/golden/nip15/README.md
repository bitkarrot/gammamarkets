# Golden NIP-15 fixtures (D-08)

Literal 30017/30018 DTO payloads per section 6.6 plus the
invalid variants the validator must reject:

- `stall_30017.json` — valid stall incl. the deterministic
  zero-cost `digital` zone
- `product_30018.json` — valid product (specs as pair
  arrays, integer quantity)
- `product_30018_unlimited.json` — quantity null (unlimited)
- `product_30018_hidden.json` — hidden/pre-order mapped to
  quantity 0
- `order_physical_opaque_address.json` — type-2 order with
  an opaque address payload
- `invalid_specs_object.json` — specs as object, not pairs
- `invalid_quantity_float.json` /
  `invalid_quantity_string.json` — non-integer quantity
- `invalid_missing_shipping_id.json` — zone without id
- `invalid_mismatched_currency.json` — product currency
  differs from the stall's (compatibility-preview error)

## Regeneration

    uv run python tests/fixtures/golden/generate_fixtures.py

Fixed identifiers: stall d=`gq-stall-0001`, shipping
d=`gq-ship-dom`, product d=`gq-prod-0001`.
