from decimal import Decimal, ROUND_HALF_UP
from flask import current_app


def calc_rate(provider_rate: Decimal, markup_percent=None) -> Decimal:
    """
    Calculate the customer-facing rate (per 1000) from the provider's raw
    rate, applying either a per-service markup or the global default.
    """
    if markup_percent is None:
        markup_percent = Decimal(str(current_app.config["DEFAULT_MARKUP_PERCENT"]))
    else:
        markup_percent = Decimal(str(markup_percent))

    provider_rate = Decimal(str(provider_rate))
    multiplier = (Decimal("100") + markup_percent) / Decimal("100")
    rate = provider_rate * multiplier
    return rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calc_charge(rate_per_1000: Decimal, quantity: int) -> Decimal:
    """Charge = rate_per_1000 * quantity / 1000, rounded to cents."""
    rate_per_1000 = Decimal(str(rate_per_1000))
    charge = (rate_per_1000 * Decimal(quantity)) / Decimal("1000")
    return charge.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
