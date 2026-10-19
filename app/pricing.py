"""Pure tier-pricing helpers (no I/O)."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

Tier = tuple[int, Decimal]  # (min_qty, unit_price)


class MOQError(ValueError):
    """Requested quantity is invalid or below the minimum order quantity."""


def unit_price_for_qty(qty: int, tiers: Iterable[Tier], base_price: Decimal, moq: int = 1) -> Decimal:
    """Unit price for qty: price of the highest tier whose min_qty <= qty.

    Falls back to base_price when no tier applies. Raises MOQError if qty < 1 or qty < moq.
    """
    if qty < 1:
        raise MOQError("quantity must be at least 1")
    if qty < moq:
        raise MOQError(f"quantity {qty} is below the minimum order quantity {moq}")
    best: Tier | None = None
    for tier in tiers:
        if tier[0] <= qty and (best is None or tier[0] > best[0]):
            best = tier
    return Decimal(best[1] if best else base_price)


def line_total(qty: int, unit_price: Decimal) -> Decimal:
    """qty * unit_price rounded half-up to cents."""
    return (Decimal(unit_price) * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
