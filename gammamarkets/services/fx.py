"""Section 3.4 FX boundary — Decimal-only past the ``btc_rates`` adapter.

Provider floats cross into ``Decimal`` EXACTLY ONCE via
``Decimal(str(value))`` at this boundary; everything downstream is Decimal
arithmetic. We never call the host's cached ``fiat_amount_as_satoshis``
helper or inherit its ``int()`` truncation.

Conversion is ``amount_minor / 10**currency_decimals * sat_per_major_unit``
with ``ROUND_CEILING`` per line and per shipping component; the order total
is the checked integer sum and ``total_sat >= 1`` is required. One
``order_fx_quotes`` row per source currency persists decimal-string values,
provider names, direction/units, observed/expiry timestamps, and source.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from lnbits.utils.exchange_rates import btc_rates

SAT_PER_BTC = Decimal(100_000_000)
QUOTE_TTL_S = 300  # five-minute freshness (section 3.4)
INT64_MAX = 2**63 - 1


class FxRejection(Exception):
    """A quote or conversion failed validation. Bounded reason codes only."""


def _reject(reason: str) -> None:
    raise FxRejection(reason)


@dataclass(frozen=True)
class FxQuote:
    currency: str
    currency_per_btc: Decimal
    sat_per_major_unit: Decimal
    providers: tuple[str, ...]
    observed_at: int
    expires_at: int
    source: str = "btc_rates"


async def quote_currency(currency: str) -> FxQuote:
    """Call the host's uncached ``btc_rates`` and build a §3.4 quote.

    Each provider float crosses into Decimal exactly once. Failed,
    nonfinite, or nonpositive provider values are filtered before the mean;
    an empty filtered set is rejected (``quote-no-provenance``).
    """
    try:
        provider_values = await btc_rates(currency)
    except Exception as exc:
        raise FxRejection("quote-provider-failed") from exc

    provider_names: list[str] = []
    values: list[Decimal] = []
    for name, raw in provider_values:
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        if isinstance(raw, float) and not math.isfinite(raw):
            continue
        value = Decimal(str(raw))  # the single float->Decimal crossing
        if not value.is_finite() or value <= 0:
            continue
        provider_names.append(name)
        values.append(value)

    if not provider_names:
        _reject("quote-no-provenance")
    if not currency or not currency.isalpha() or len(currency) != 3:
        _reject("quote-currency-invalid")

    mean = sum(values) / Decimal(len(values))
    if not mean.is_finite():
        _reject("quote-nonfinite")
    if mean <= 0:
        _reject("quote-nonpositive")

    observed = int(time.time())
    return FxQuote(
        currency=currency.upper(),
        currency_per_btc=mean,
        sat_per_major_unit=SAT_PER_BTC / mean,
        providers=tuple(provider_names),
        observed_at=observed,
        expires_at=observed + QUOTE_TTL_S,
    )


def sat_quote() -> FxQuote:
    """A same-currency quote: 1 sat = 1 sat, no provider call needed."""
    now = int(time.time())
    return FxQuote(
        currency="SAT",
        currency_per_btc=SAT_PER_BTC,
        sat_per_major_unit=Decimal(1),
        providers=("identity",),
        observed_at=now,
        expires_at=now + QUOTE_TTL_S,
        source="identity",
    )


def require_usable_quote(quote: FxQuote | None, *, now: int) -> FxQuote:
    """Rejection-before-reservation gate (section 3.4)."""
    if quote is None:
        _reject("quote-empty")
    if not quote.providers:
        _reject("quote-no-provenance")
    if not quote.currency_per_btc.is_finite() or not (
        quote.sat_per_major_unit.is_finite()
    ):
        _reject("quote-nonfinite")
    if quote.currency_per_btc <= 0 or quote.sat_per_major_unit <= 0:
        _reject("quote-nonpositive")
    if now >= quote.expires_at:
        _reject("quote-stale")
    return quote


def convert_minor_to_sat(
    quote: FxQuote, *, amount_minor: int, currency_decimals: int,
    now: int | None = None,
) -> int:
    """``amount_minor / 10**decimals * sat_per_major_unit``, ROUND_CEILING."""
    require_usable_quote(
        quote, now=quote.observed_at if now is None else now
    )
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        _reject("amount-minor-not-int")
    if amount_minor < 0:
        _reject("amount-minor-negative")
    if currency_decimals < 0:
        _reject("currency-decimals-negative")
    major = Decimal(amount_minor) / (Decimal(10) ** currency_decimals)
    sat = (major * quote.sat_per_major_unit).to_integral_value(
        rounding=ROUND_CEILING
    )
    return int(sat)


def convert_line(
    quote: FxQuote, *, currency: str, amount_minor: int,
    currency_decimals: int, now: int | None = None,
) -> int:
    """Convert ONE cart line or shipping component in ``currency`` — a line
    whose currency does not match the quote is rejected (currencies never
    mix, §3.4/decision 21.9)."""
    if currency != quote.currency:
        _reject("currency-mismatch")
    return convert_minor_to_sat(
        quote, amount_minor=amount_minor,
        currency_decimals=currency_decimals, now=now,
    )


def checked_total_sat(components: list[int]) -> int:
    """The checked integer sum of per-line/per-shipping sat components."""
    total = 0
    for component in components:
        if not isinstance(component, int) or isinstance(component, bool):
            _reject("component-not-int")
        if component < 0:
            _reject("component-negative")
        total += component
        if total > INT64_MAX:
            _reject("total-overflow")
    if total < 1:
        _reject("total-sat-below-1")
    return total


async def persist_quote(tx, order_id: str, quote: FxQuote) -> None:
    """One ``order_fx_quotes`` row per source currency (§3.4/§4.7)."""
    await tx.execute(
        f"INSERT INTO {tx.table('order_fx_quotes')} "
        "(id, order_id, currency, rate_decimal, rate_direction, rate_unit,"
        " source, providers, quoted_at, expires_at) "
        "VALUES (:i, :o, :c, :rd, :rdir, :ru, :s, :p, :q, :e)",
        {
            "i": uuid.uuid4().hex,
            "o": order_id,
            "c": quote.currency,
            "rd": str(quote.sat_per_major_unit),
            "rdir": "sat_per_major_unit",
            "ru": f"sat/{quote.currency}",
            "s": quote.source,
            "p": ",".join(quote.providers),
            "q": quote.observed_at,
            "e": quote.expires_at,
        },
    )
