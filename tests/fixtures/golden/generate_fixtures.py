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


async def main() -> None:
    buyer = sdk.fixed_test_keys("buyer")
    merchant = sdk.fixed_test_keys("merchant")
    await gen_nip17(buyer, merchant)
    await gen_nip89(merchant)
    print(f"fixtures written under {FIXTURE_ROOT}")


if __name__ == "__main__":
    asyncio.run(main())
