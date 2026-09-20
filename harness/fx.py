"""Section 3.4 FX boundary model — Decimal-only past the adapter edge.

Provider floats cross into the model EXACTLY ONCE via ``Decimal(str(value))``
at the adapter boundary; everything downstream is ``Decimal`` arithmetic.
The model never calls the host's cached ``fiat_amount_as_satoshis`` helper
and never inherits its ``int()`` truncation (STACK.md non-selection;
T-03-06).

Contract (section 3.4):

- ``FxQuote(currency, currency_per_btc, sat_per_major_unit, providers,
  observed_at, expires_at)`` — numeric values are ``Decimal``, ``providers``
  is nonempty, ``sat_per_major_unit = Decimal(100_000_000) /
  currency_per_btc``, ``observed_at`` is the UTC completion time,
  ``expires_at = observed_at + 5 minutes``.
- ``currency_per_btc`` is the Decimal arithmetic mean of the filtered
  provider values returned by ``btc_rates``.
- Conversion ``amount_minor / 10**currency_decimals * sat_per_major_unit``
  with ``ROUND_CEILING`` per line and per shipping component; the order
  total is the checked integer sum; ``total_sat >= 1`` is required.
- Empty, zero, nonfinite, failed, provenance-free, or stale quotes reject
  checkout BEFORE any reservation row or stock increment exists.
- One ``order_fx_quotes`` row per source currency persists decimal-string
  values, provider names, direction/units, observed/expiry timestamps, and
  source.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from fractions import Fraction

SAT_PER_BTC = Decimal(100_000_000)
QUOTE_TTL_S = 300  # five-minute freshness (section 3.4)

#: Checked 64-bit signed bound for computed amounts (section 15).
INT64_MAX = 2**63 - 1


class FxRejection(Exception):
    """A quote or conversion failed validation. Bounded reason codes only."""


def _reject(reason: str) -> None:
    raise FxRejection(reason)


@dataclass(frozen=True)
class FxQuote:
    """A fresh multi-provider quote (section 3.4)."""

    currency: str
    currency_per_btc: Decimal
    sat_per_major_unit: Decimal
    providers: tuple[str, ...]
    observed_at: int
    expires_at: int
    source: str = "btc_rates"


def quote_from_provider_floats(
    currency: str,
    provider_values: list[tuple[str, float]],
    *,
    observed_at: int,
    source: str = "btc_rates",
) -> FxQuote:
    """Build a quote from raw provider floats — the adapter boundary.

    Each provider float crosses into Decimal exactly once via
    ``Decimal(str(value))``. Failed/NaN/infinite/nonpositive provider values
    are filtered BEFORE the mean; an empty filtered set is rejected.
    ``observed_at`` is the UTC completion time of the provider call.
    """
    provider_names: list[str] = []
    values: list[Decimal] = []
    for name, raw in provider_values:
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue  # failed provider value — filtered
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

    return FxQuote(
        currency=currency,
        currency_per_btc=mean,
        sat_per_major_unit=SAT_PER_BTC / mean,
        providers=tuple(provider_names),
        observed_at=observed_at,
        expires_at=observed_at + QUOTE_TTL_S,
        source=source,
    )


def require_usable_quote(quote: FxQuote | None, *, now: int) -> FxQuote:
    """Rejection-before-reservation gate (section 3.4).

    Empty, zero, nonfinite, provenance-free, or stale quotes are rejected
    BEFORE any reservation row or stock increment may exist.
    """
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
    quote: FxQuote,
    *,
    amount_minor: int,
    currency_decimals: int,
    now: int | None = None,
) -> int:
    """``amount_minor / 10**decimals * sat_per_major_unit``, ROUND_CEILING.

    Applied independently per line and per shipping component — never on a
    pre-summed float (section 3.4, decision 21.9: currencies never mix).
    ``now`` defaults to the quote's observation time; the caller passes the
    wall-clock time so a stale quote rejects at the conversion edge too.
    """
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
    quote: FxQuote,
    *,
    currency: str,
    amount_minor: int,
    currency_decimals: int,
    now: int | None = None,
) -> int:
    """Convert ONE cart line or shipping component in ``currency``.

    Section 3.4 / decision 21.9: currencies never arithmetically mix —
    every line converts with the quote for its own currency. A line whose
    currency does not match the quote is rejected rather than silently
    converted at the wrong rate.
    """
    if currency != quote.currency:
        _reject("currency-mismatch")
    return convert_minor_to_sat(
        quote,
        amount_minor=amount_minor,
        currency_decimals=currency_decimals,
        now=now,
    )


def checked_total_sat(components: list[int]) -> int:
    """The checked integer sum of per-line/per-shipping sat components.

    Rejects negative components, non-integer components, and any total
    exceeding the signed 64-bit bound (section 15). ``total_sat >= 1`` is
    required — amountless invoices are rejected.
    """
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


def insert_order_fx_quote_sql(table: str) -> str:
    """One ``order_fx_quotes`` row per source currency (section 3.4)."""
    return (
        f"INSERT INTO {table}"
        " (order_id, currency, rate_decimal, rate_direction, rate_unit,"
        " source, providers, quoted_at, expires_at)"
        " VALUES (:order_id, :currency, :rate_decimal, :rate_direction,"
        " :rate_unit, :source, :providers, :quoted_at, :expires_at)"
    )


def order_fx_quote_row(order_id: str, quote: FxQuote) -> dict:
    """The persisted row: decimal-string rate, provider names, direction and
    units, observed/expiry timestamps, and source (section 3.4)."""
    return {
        "order_id": order_id,
        "currency": quote.currency,
        "rate_decimal": str(quote.sat_per_major_unit),
        "rate_direction": "sat_per_major_unit",
        "rate_unit": f"sat/{quote.currency}",
        "source": quote.source,
        "providers": ",".join(quote.providers),
        "quoted_at": quote.observed_at,
        "expires_at": quote.expires_at,
    }


# --- float-boundary measurement (section 3.4 Phase-0 requirement) -------------

MEASUREMENT_SEED = 20260920


#: Deterministic conversion scenario used for the absolute sat-error bound:
#: 1000.00 major units of a 2-decimal currency (100_000 minor units).
_MEASURE_AMOUNT_MINOR = 100_000
_MEASURE_CURRENCY_DECIMALS = 2


def measure_float_boundary_error(
    provider_values: list[tuple[str, float]],
) -> dict:
    """Measure the adapter-boundary error of ``Decimal(str(float))``.

    Compares the Decimal(str(v)) conversion and arithmetic mean against
    exact rational arithmetic (Fraction of the same float bits) over the
    seeded sample, AND measures the resulting difference in the ceiling-
    converted sat amount for a fixed conversion scenario. Returns the
    maximum per-value and aggregate relative errors plus the worst-case
    absolute sat error — all JSON-safe for the evidence manifest and
    PINS.md.
    """
    if not provider_values:
        _reject("measurement-empty")
    per_value_max = Fraction(0)
    dec_sum = Decimal(0)
    exact_sum = Fraction(0)
    worst_case = ""
    max_abs_sat_error = 0
    scale = Fraction(10) ** _MEASURE_CURRENCY_DECIMALS
    for name, raw in provider_values:
        dec = Decimal(str(raw))
        exact = Fraction(raw)
        if exact == 0:
            continue
        err = abs(Fraction(dec) - exact) / abs(exact)
        if err >= per_value_max:
            worst_case = f"{name}={raw!r}"
        per_value_max = max(per_value_max, err)
        dec_sum += dec
        exact_sum += exact
        # Simulated conversion difference: Decimal pipeline vs exact
        # rational pipeline, same ROUND_CEILING semantics.
        dec_sat = int(
            (Decimal(_MEASURE_AMOUNT_MINOR) / (Decimal(10) ** _MEASURE_CURRENCY_DECIMALS)
             * (SAT_PER_BTC / dec)).to_integral_value(rounding=ROUND_CEILING)
        )
        exact_sat_raw = (
            Fraction(_MEASURE_AMOUNT_MINOR) / scale
            * (Fraction(100_000_000) / exact)
        )
        exact_sat = (
            exact_sat_raw.numerator + exact_sat_raw.denominator - 1
        ) // exact_sat_raw.denominator
        max_abs_sat_error = max(max_abs_sat_error, abs(dec_sat - exact_sat))
    n = Decimal(len(provider_values))
    mean_rel = (
        abs(Fraction(dec_sum / n) - exact_sum / len(provider_values))
        / abs(exact_sum / len(provider_values))
        if exact_sum
        else Fraction(0)
    )
    return {
        "seed": MEASUREMENT_SEED,
        "samples": len(provider_values),
        "scenario": (
            f"{_MEASURE_AMOUNT_MINOR} minor units, "
            f"{_MEASURE_CURRENCY_DECIMALS} decimals, ROUND_CEILING"
        ),
        "max_value_relative_error": float(per_value_max),
        "mean_relative_error": float(mean_rel),
        "max_relative_error": float(max(per_value_max, mean_rel)),
        "max_abs_sat_error": max_abs_sat_error,
        "worst_case": worst_case,
    }


def seeded_float_sample() -> list[tuple[str, float]]:
    """A deterministic sample of representative provider floats, including
    values whose binary representation carries well-known error."""
    import random

    rng = random.Random(MEASUREMENT_SEED)
    sample: list[tuple[str, float]] = [
        ("p-exact-power", 65536.0),
        ("p-tenth", 0.1),  # classic binary-representation error
        ("p-price", 43210.987654321),
        ("p-third-ish", 1.0 / 3.0),
        ("p-large", 999_999_999.9999999),
        ("p-small", 0.00004242),
    ]
    for i in range(24):
        # random plausible fiat-per-BTC magnitudes with full f64 mantissa
        sample.append((f"rng-{i}", rng.uniform(1.0, 250_000.0)))
    return sample
