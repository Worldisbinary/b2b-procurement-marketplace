from decimal import Decimal as D

import pytest

from app.pricing import MOQError, line_total, unit_price_for_qty

TIERS = [(10, D("10.00")), (50, D("9.00")), (100, D("8.00"))]
BASE = D("11.00")


def price(qty, tiers=TIERS, base=BASE, moq=10):
    return unit_price_for_qty(qty, tiers, base, moq)


def test_moq_boundary_uses_first_tier():
    assert price(10) == D("10.00")


def test_between_tiers_uses_lower_tier():
    assert price(49) == D("10.00")


def test_exact_tier_boundary_uses_that_tier():
    assert price(50) == D("9.00")
    assert price(100) == D("8.00")


def test_above_highest_tier():
    assert price(10_000) == D("8.00")


def test_unsorted_tiers():
    assert price(75, tiers=[(100, D("8")), (10, D("10")), (50, D("9"))]) == D("9")


def test_below_moq_raises():
    with pytest.raises(MOQError):
        price(9)


def test_zero_and_negative_raise():
    for q in (0, -5):
        with pytest.raises(MOQError):
            price(q, moq=1)


def test_no_tiers_returns_base_price():
    assert price(20, tiers=[]) == BASE


def test_no_tier_applies_falls_back_to_base():
    # moq below the first tier's min_qty
    assert unit_price_for_qty(2, [(10, D("10"))], BASE, moq=1) == BASE


def test_moq_error_is_value_error():
    assert issubclass(MOQError, ValueError)


def test_line_total_basic():
    assert line_total(50, D("9.00")) == D("450.00")


def test_line_total_rounds_half_up():
    assert line_total(3, D("0.335")) == D("1.01")  # 1.005 -> 1.01


def test_line_total_quantizes_to_cents():
    assert str(line_total(2, D("1.5"))) == "3.00"
