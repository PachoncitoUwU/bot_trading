"""Unit Tests for Decimal Financial Math Module."""
from decimal import Decimal
import pytest
from app.core.constants import OrderSide
from app.core.decimal_math import (
    to_decimal,
    round_to_step_size,
    round_to_tick_size,
    validate_min_notional,
    calculate_fee,
    apply_slippage,
    calculate_pnl,
)


def test_to_decimal_conversions():
    assert to_decimal(10.5) == Decimal("10.5")
    assert to_decimal("0.000123") == Decimal("0.000123")
    assert to_decimal(None) == Decimal("0")
    assert to_decimal("") == Decimal("0")
    assert to_decimal(Decimal("55.1")) == Decimal("55.1")


def test_round_to_step_size_never_overshoots():
    # 0.12345 with step 0.001 must round DOWN to 0.123 (never 0.124)
    step = Decimal("0.001")
    assert round_to_step_size("0.12345", step) == Decimal("0.123")
    assert round_to_step_size("0.12399", step) == Decimal("0.123")
    # Exact step boundary test
    assert round_to_step_size("1.000", step) == Decimal("1.000")
    assert round_to_step_size("0.005", step) == Decimal("0.005")
    # Sub-step test (smaller than step size -> 0)
    assert round_to_step_size("0.00099", step) == Decimal("0.000")


def test_round_to_tick_size():
    # Price rounding to nearest tick
    tick = Decimal("0.01")
    assert round_to_tick_size("65432.174", tick) == Decimal("65432.17")
    assert round_to_tick_size("65432.176", tick) == Decimal("65432.18")
    assert round_to_tick_size("65432.175", tick) == Decimal("65432.18")
    # Exact tick boundary
    assert round_to_tick_size("100.50", tick) == Decimal("100.50")


def test_validate_min_notional_edge_cases():
    min_notional = Decimal("5.00000000")
    # Exactly $5.000000 -> True
    assert validate_min_notional("50.00", "0.10", min_notional) is True
    # $4.999999 -> False
    assert validate_min_notional("49.99999", "0.10", min_notional) is False
    # $5.000001 -> True
    assert validate_min_notional("50.00001", "0.10", min_notional) is True


def test_apply_slippage_bidirectional():
    price = Decimal("100.0")
    slippage_pct = Decimal("0.5")  # 0.5%
    
    # BUY order slips UPWARD (+) to 100.50
    buy_slipped = apply_slippage(price, slippage_pct, OrderSide.BUY)
    assert buy_slipped == Decimal("100.500")
    assert buy_slipped > price

    # SELL order slips DOWNWARD (-) to 99.50
    sell_slipped = apply_slippage(price, slippage_pct, OrderSide.SELL)
    assert sell_slipped == Decimal("99.500")
    assert sell_slipped < price


def test_calculate_fee():
    notional = Decimal("1000.00")
    fee_rate = Decimal("0.001")  # 0.1%
    assert calculate_fee(notional, fee_rate) == Decimal("1.00000000")


def test_calculate_pnl():
    # Long trade: buy at 100, sell at 110 with 2 units -> +20
    assert calculate_pnl("100", "110", "2", OrderSide.BUY) == Decimal("20")
    # Short / inverse trade
    assert calculate_pnl("110", "100", "2", OrderSide.SELL) == Decimal("20")
    # Loss trade: buy at 100, sell at 90 with 1 unit -> -10
    assert calculate_pnl("100", "90", "1", OrderSide.BUY) == Decimal("-10")
