"""Generate the checked-in golden protocol fixtures (D-08).

Run once (or to regenerate) with:

    uv run python tests/fixtures/golden/generate_fixtures.py

Deterministic inputs (fixed synthetic keys, pinned rumor created_at, fixed
identifiers) make the INPUTS fully reproducible. Seal/wrap outputs are one
frozen generation of the NIP-59 pipeline: the pinned SDK generates a fresh
ephemeral wrapper key and randomized past timestamps per copy, so
regeneration produces equivalent-but-different seal/wrap ciphertexts — the
checked-in files are the frozen reference (D-08), not a byte-stable recipe.

All keys are synthetic test keys (``sha256("gammamarkets-qual:<role>")``);
no real key material is ever present in this tree.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import nostr_sdk as ns

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from harness import sdk  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parent

# Fixed identifiers (deterministic inputs).
RUMOR_CREATED_AT = 1_750_000_000  # pinned rumor timestamp (real-time at "send")
ORDER_EXTERNAL_ID = "gq-order-01"
PRODUCT_D = "gq-prod-0001"
RECOMMENDED_APP_D = "gqapp-rec-001"
SEED_NOTE = (
    "keys = sha256('gammamarkets-qual:'+role); rumor created_at=1750000000; "
    "order external id=gq-order-01; product d=gq-prod-0001; "
    "recommended_app_d=gqapp-rec-001"
)


def _event_json(event) -> dict:
    return json.loads(event.as_json())


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload + "\n")
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


async def gen_nip17(buyer: ns.Keys, merchant: ns.Keys) -> None:
    """Golden NIP-17 two-copy chain: rumor + per-copy seal/wrap + retry."""
    out = FIXTURE_ROOT / "nip17"
    rumor = sdk.build_order_rumor(
        merchant,  # merchant-authored: outbound copy semantics (section 6.9)
        buyer.public_key(),
        order_external_id=ORDER_EXTERNAL_ID,
        amount_sat=12500,
        items=[(f"30402:{merchant.public_key().to_hex()}:{PRODUCT_D}", 2)],
        created_at=RUMOR_CREATED_AT,
        content="Qualification fixture order message",
    )
    _write(out / "rumor.json", json.loads(rumor.as_json()))

    # Recipient copy (addressed to the buyer) and sender copy (to merchant).
    r_seal, r_wrap = await sdk.wrap_order_copy(merchant, buyer.public_key(), rumor)
    s_seal, s_wrap = await sdk.wrap_order_copy(
        merchant, merchant.public_key(), rumor
    )
    _write(out / "recipient" / "seal.json", _event_json(r_seal))
    _write(out / "recipient" / "wrap.json", _event_json(r_wrap))
    _write(out / "sender" / "seal.json", _event_json(s_seal))
    _write(out / "sender" / "wrap.json", _event_json(s_wrap))

    # Retry of the recipient copy: same rumor, fresh seal/wrap/outer ids.
    t_seal, t_wrap = await sdk.wrap_order_copy(merchant, buyer.public_key(), rumor)
    _write(out / "retry" / "seal.json", _event_json(t_seal))
    _write(out / "retry" / "wrap.json", _event_json(t_wrap))

    # Kind-14 general-DM rumor (merchant -> buyer) and kind-17 receipt rumor
    # (buyer -> merchant): unsigned rumor fixtures for the section-6.9
    # allowlist coverage required by the P0-14 registry.
    kind14 = (
        ns.EventBuilder(ns.Kind(14), "Qualification fixture DM")
        .custom_created_at(ns.Timestamp.from_secs(RUMOR_CREATED_AT))
        .tags(
            [
                ns.Tag.parse(["p", buyer.public_key().to_hex()]),
                ns.Tag.parse(["subject", ORDER_EXTERNAL_ID]),
            ]
        )
        .build(merchant.public_key())
    )
    _write(out / "rumor_kind14.json", json.loads(kind14.as_json()))

    kind17 = (
        ns.EventBuilder(ns.Kind(17), "")
        .custom_created_at(ns.Timestamp.from_secs(RUMOR_CREATED_AT))
        .tags(
            [
                ns.Tag.parse(["p", merchant.public_key().to_hex()]),
                ns.Tag.parse(["order", ORDER_EXTERNAL_ID]),
                ns.Tag.parse(
                    [
                        "payment",
                        "lightning",
                        "lnbc125n1pjfixture000000000000000000000000000000",
                        "ab" * 32,
                    ]
                ),
                ns.Tag.parse(["amount", "12500"]),
            ]
        )
        .build(buyer.public_key())
    )
    _write(out / "rumor_kind17.json", json.loads(kind17.as_json()))

    _write(
        out / "keys.json",
        {
            "note": "synthetic test keys only — never real key material",
            "buyer_secret_hex": hashlib.sha256(
                b"gammamarkets-qual:buyer"
            ).hexdigest(),
            "buyer_pubkey": buyer.public_key().to_hex(),
            "merchant_secret_hex": hashlib.sha256(
                b"gammamarkets-qual:merchant"
            ).hexdigest(),
            "merchant_pubkey": merchant.public_key().to_hex(),
        },
    )


async def gen_nip89(merchant: ns.Keys) -> None:
    """Golden NIP-89 handler pair + a valid kind-30402 naddr (sections 6.5)."""
    out = FIXTURE_ROOT / "nip89"
    signer = ns.NostrSigner.keys(merchant)
    mpk = merchant.public_key().to_hex()

    handler = await (
        ns.EventBuilder(ns.Kind(31990), json.dumps(
            {
                "name": "GammaMarkets checkout",
                "about": "LNbits gammamarkets extension checkout handler",
                "picture": "",
            },
            sort_keys=True,
        ))
        .tags(
            [
                ns.Tag.parse(["d", RECOMMENDED_APP_D]),
                ns.Tag.parse(["k", "30402"]),
                ns.Tag.parse(
                    ["web", "https://shop.example/gammamarkets/p/<bech32>", "naddr"]
                ),
            ]
        )
        .sign(signer)
    )
    recommendation = await (
        ns.EventBuilder(ns.Kind(31989), "")
        .tags(
            [
                # The supported event KIND, not the app id (section 6.5).
                ns.Tag.parse(["d", "30402"]),
                ns.Tag.parse(
                    [
                        "a",
                        f"31990:{mpk}:{RECOMMENDED_APP_D}",
                        "wss://relay.example.com",
                        "web",
                    ]
                ),
            ]
        )
        .sign(signer)
    )
    _write(out / "handler_31990.json", _event_json(handler))
    _write(out / "recommendation_31989.json", _event_json(recommendation))

    coord = ns.Nip19Coordinate(
        ns.Coordinate(ns.Kind(30402), merchant.public_key(), identifier=PRODUCT_D),
        [ns.RelayUrl.parse("wss://relay.example.com")],
    )
    _write(out / "naddr.txt", coord.to_bech32())


STALL_D = "gq-stall-0001"
SHIPPING_D = "gq-ship-dom"


def gen_nip15() -> None:
    """Literal NIP-15 DTO fixtures (section 6.6) — content JSON shapes.

    These are the literal DTO payloads the 30017/30018 events carry in their
    content fields, plus the invalid variants the validator must reject and
    the compatibility shapes (opaque physical-order address, mismatched
    currencies, hidden/pre-order quantity mapping, digital zero-cost zone).
    """
    out = FIXTURE_ROOT / "nip15"

    stall = {
        "id": STALL_D,
        "name": "Qualification Stall",
        "description": "Stall fixture for the qualification harness",
        "currency": "USD",
        "shipping": [
            {
                "id": SHIPPING_D,
                "name": "Domestic",
                "cost": 5.0,
                "regions": ["US", "CA"],
            },
            {
                # Deterministic zero-cost zone required when a stall
                # contains digital products (section 6.6).
                "id": "digital",
                "name": "Digital delivery",
                "cost": 0,
                "regions": ["Worldwide"],
            },
        ],
    }
    _write(out / "stall_30017.json", stall)

    product = {
        "id": PRODUCT_D,
        "stall_id": STALL_D,
        "name": "Qualification Product",
        "description": "Product fixture",
        "images": [],
        "currency": "USD",
        "price": 19.99,
        "quantity": 3,
        "specs": [["size", "M"], ["color", "black"]],
        "shipping": [{"id": SHIPPING_D, "cost": 0}],
    }
    _write(out / "product_30018.json", product)

    unlimited = dict(product)
    unlimited["id"] = "gq-prod-unlim1"
    unlimited["quantity"] = None
    _write(out / "product_30018_unlimited.json", unlimited)

    hidden = dict(product)
    hidden["id"] = "gq-prod-hidden"
    # hidden / pre-order -> quantity 0 (NIP-15 has no visibility flag).
    hidden["quantity"] = 0
    _write(out / "product_30018_hidden.json", hidden)

    # NIP-15 physical order shape: the address is an OPAQUE payload the
    # merchant interprets — never parsed into fields by the protocol layer.
    order = {
        "id": "gq-nip15-order-01",
        "type": 2,
        "name": "Buyer Name",
        "address": "123 Opaque St, Unit 4, Springfield 00000",
        "message": "leave at door",
        "contact": {"nostr": "", "phone": "+15551230000", "email": ""},
        "items": [{"product_id": PRODUCT_D, "quantity": 1}],
        "shipping_id": SHIPPING_D,
    }
    _write(out / "order_physical_opaque_address.json", order)

    # Invalid variants — each violates exactly one literal rule.
    bad_specs = dict(product)
    bad_specs["specs"] = {"size": "M"}  # object, not pair array
    _write(out / "invalid_specs_object.json", bad_specs)

    bad_qty_float = dict(product)
    bad_qty_float["quantity"] = 1.5
    _write(out / "invalid_quantity_float.json", bad_qty_float)

    bad_qty_str = dict(product)
    bad_qty_str["quantity"] = "3"
    _write(out / "invalid_quantity_string.json", bad_qty_str)

    bad_shipping = dict(product)
    bad_shipping["shipping"] = [{"cost": 0}]  # missing id
    _write(out / "invalid_missing_shipping_id.json", bad_shipping)

    bad_currency = dict(product)
    bad_currency["currency"] = "EUR"  # stall is USD — preview error
    _write(out / "invalid_mismatched_currency.json", bad_currency)

    _write(
        out / "README.md",
        "\n".join(
            [
                "# Golden NIP-15 fixtures (D-08)",
                "",
                "Literal 30017/30018 DTO payloads per section 6.6 plus the",
                "invalid variants the validator must reject:",
                "",
                "- `stall_30017.json` — valid stall incl. the deterministic",
                "  zero-cost `digital` zone",
                "- `product_30018.json` — valid product (specs as pair",
                "  arrays, integer quantity)",
                "- `product_30018_unlimited.json` — quantity null (unlimited)",
                "- `product_30018_hidden.json` — hidden/pre-order mapped to",
                "  quantity 0",
                "- `order_physical_opaque_address.json` — type-2 order with",
                "  an opaque address payload",
                "- `invalid_specs_object.json` — specs as object, not pairs",
                "- `invalid_quantity_float.json` /",
                "  `invalid_quantity_string.json` — non-integer quantity",
                "- `invalid_missing_shipping_id.json` — zone without id",
                "- `invalid_mismatched_currency.json` — product currency",
                "  differs from the stall's (compatibility-preview error)",
                "",
                "## Regeneration",
                "",
                "    uv run python tests/fixtures/golden/generate_fixtures.py",
                "",
                "Fixed identifiers: stall d=`gq-stall-0001`, shipping",
                "d=`gq-ship-dom`, product d=`gq-prod-0001`.",
            ]
        ),
    )


async def main() -> None:
    buyer = sdk.fixed_test_keys("buyer")
    merchant = sdk.fixed_test_keys("merchant")
    await gen_nip17(buyer, merchant)
    await gen_nip89(merchant)
    gen_nip15()
    print(f"fixtures written under {FIXTURE_ROOT}")


if __name__ == "__main__":
    asyncio.run(main())
