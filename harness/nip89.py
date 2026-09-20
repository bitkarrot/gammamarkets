"""Local-only NIP-89 / naddr resolution model (spec sections 5.4, 6.5).

The resolver decodes a bech32 ``naddr`` through the pinned SDK's NIP-19 API
and resolves it against a fixture registry mapping ``(merchant_pubkey, d)``
to a local canonical product page. It NEVER performs network I/O: embedded
relay hints are recorded on the result (so tests can assert they exist and
were ignored) but no code path exists that could fetch one (T-03-02).

Rejection reasons are bounded codes — no event payloads or bech32 strings
are embedded in errors (same quarantine discipline as ``harness.sdk``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nostr_sdk import Nip19Coordinate

# Section 3.1: protocol-visible ``d`` alphabet — lowercase hex or
# ``[a-z0-9-]`` slugs, length 8-64 chars.
D_TAG_RE = re.compile(r"^[a-z0-9-]{8,64}$")

KIND_PRODUCT = 30402
KIND_HANDLER_INFO = 31990
KIND_HANDLER_RECOMMENDATION = 31989

#: Canonical buyer-facing product page path (section 5.4 route table under
#: the frozen ``/gammamarkets`` route prefix).
CANONICAL_PAGE_TEMPLATE = "/gammamarkets/p/{pubkey}/{d}"


class NaddrRejection(Exception):
    """A naddr or NIP-89 pair failed validation. Message is a bounded code."""


def _reject(reason: str) -> None:
    raise NaddrRejection(reason)


@dataclass(frozen=True)
class LocalCatalogRegistry:
    """Fixture registry: local merchants and their published product pages.

    ``merchant_pubkeys`` — hex pubkeys of merchants hosted by this instance.
    ``pages`` — ``(merchant_pubkey_hex, product_d) -> local canonical path``.
    """

    merchant_pubkeys: frozenset[str]
    pages: dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedNaddr:
    """Result of a successful local naddr resolution.

    ``relay_hints`` are recorded verbatim from the bech32 payload for
    evidence — they are never dereferenced.
    """

    pubkey: str
    d: str
    path: str
    relay_hints: tuple[str, ...]


def resolve_naddr(naddr: str, registry: LocalCatalogRegistry) -> ResolvedNaddr:
    """Resolve a bech32 naddr to a local canonical page (section 5.4).

    Rules, in order:

    1. bech32 must decode as a NIP-19 ``naddr`` coordinate;
    2. coordinate kind must be 30402 (product);
    3. the merchant pubkey must be hosted locally;
    4. the ``d`` identifier must satisfy the section 3.1 alphabet/length;
    5. the ``(pubkey, d)`` page must exist in the local registry.

    Malformed, wrong-kind, foreign-merchant, and unmapped references each
    fail with a distinct bounded reason — without relay retrieval.
    """
    try:
        coord = Nip19Coordinate.from_bech32(naddr.strip())
    except Exception:  # noqa: BLE001 — any decode failure is a clean reject
        _reject("naddr-malformed")

    coordinate = coord.coordinate()
    if coordinate.kind().as_u16() != KIND_PRODUCT:
        _reject("naddr-kind-not-30402")

    pubkey = coordinate.public_key().to_hex()
    if pubkey not in registry.merchant_pubkeys:
        _reject("naddr-merchant-not-local")

    d = coordinate.identifier()
    if not D_TAG_RE.match(d):
        _reject("naddr-d-invalid")

    path = registry.pages.get((pubkey, d))
    if path is None:
        _reject("naddr-product-not-local")

    hints = tuple(str(url) for url in coord.relays())
    return ResolvedNaddr(pubkey=pubkey, d=d, path=path, relay_hints=hints)


def validate_nip89_pair(
    recommendation: dict, handler: dict, merchant_pubkey: str
) -> dict:
    """Validate the section 6.5 handler pair (31989 recommendation + 31990
    handler information) as literal event dicts.

    Returns ``{"handler_d": ..., "product_kind": 30402}`` on success.
    Raises ``NaddrRejection`` with a bounded reason on failure. The pair's
    intentionally DIFFERENT ``d`` values (recommendation carries the literal
    supported kind ``"30402"``; handler carries ``recommended_app_d``) are
    asserted — a regression that equalizes them is caught here.
    """
    if recommendation.get("kind") != KIND_HANDLER_RECOMMENDATION:
        _reject("pair-rec-kind-not-31989")
    if handler.get("kind") != KIND_HANDLER_INFO:
        _reject("pair-handler-kind-not-31990")
    if recommendation.get("pubkey") != merchant_pubkey:
        _reject("pair-rec-author-not-merchant")
    if handler.get("pubkey") != merchant_pubkey:
        _reject("pair-handler-author-not-merchant")

    rec_tags = recommendation.get("tags") or []
    handler_tags = handler.get("tags") or []

    rec_d = _single_tag_value(rec_tags, "d")
    if rec_d != "30402":
        # Section 6.5: recommendation d is the supported event KIND literal,
        # not the app id.
        _reject("pair-rec-d-not-30402")

    handler_d = _single_tag_value(handler_tags, "d")
    if not handler_d:
        _reject("pair-handler-d-missing")
    if handler_d == rec_d:
        _reject("pair-d-values-not-distinct")

    a_tags = [t for t in rec_tags if _is_tag(t, "a")]
    expected_address = f"{KIND_HANDLER_INFO}:{merchant_pubkey}:{handler_d}"
    matching = [t for t in a_tags if len(t) >= 2 and t[1] == expected_address]
    if len(matching) != 1:
        _reject("pair-rec-a-tag-invalid")
    if len(matching[0]) < 4 or matching[0][3] != "web":
        _reject("pair-rec-a-tag-not-web")

    k_values = [t[1] for t in handler_tags if _is_tag(t, "k") and len(t) >= 2]
    if k_values != ["30402"]:
        _reject("pair-handler-k-tag-invalid")

    web_tags = [
        t for t in handler_tags if _is_tag(t, "web") and len(t) >= 3
    ]
    if not any("<bech32>" in t[1] and t[2] == "naddr" for t in web_tags):
        _reject("pair-handler-web-tag-invalid")

    return {"handler_d": handler_d, "product_kind": KIND_PRODUCT}


def _is_tag(tag, name: str) -> bool:
    return isinstance(tag, list) and len(tag) >= 1 and tag[0] == name


def _single_tag_value(tags, name: str) -> str | None:
    values = [t[1] for t in tags if _is_tag(t, name) and len(t) >= 2]
    if len(values) != 1:
        return None
    return values[0]
