"""Fixed-point Decimal Math Module for Financial Precision.
NEVER use float for financial calculations.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from typing import Any, Union
from app.core.constants import OrderSide


def to_decimal(value: Any) -> Decimal:
    """Safely convert any numeric value or string to Decimal."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    try:
        # String conversion is essential to prevent float precision artifacts
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert value '{value}' to Decimal: {e}")


def round_to_step_size(amount: Union[Decimal, float, str], step_size: Union[Decimal, float, str]) -> Decimal:
    """
    Rounds an order amount DOWN to the nearest valid step size for the exchange lot.
    Always rounds DOWN to guarantee that the user never attempts to sell/buy more than their balance allows.
    Example: amount=1.23456, step_size=0.001 -> 1.234
    """
    d_amount = to_decimal(amount)
    d_step = to_decimal(step_size)

    if d_step <= Decimal("0"):
        return d_amount

    # Quantize using step_size exponent
    quotient = (d_amount / d_step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return quotient * d_step


def round_to_tick_size(price: Union[Decimal, float, str], tick_size: Union[Decimal, float, str]) -> Decimal:
    """
    Rounds an order price to the nearest valid price tick.
    Example: price=65432.178, tick_size=0.01 -> 65432.18
    """
    d_price = to_decimal(price)
    d_tick = to_decimal(tick_size)

    if d_tick <= Decimal("0"):
        return d_price

    quotient = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return quotient * d_tick


def validate_min_notional(
    price: Union[Decimal, float, str],
    amount: Union[Decimal, float, str],
    min_notional: Union[Decimal, float, str]
) -> bool:
    """Checks if price * amount meets the minimum notional value (e.g. 5 USDT on Binance)."""
    d_price = to_decimal(price)
    d_amount = to_decimal(amount)
    d_min = to_decimal(min_notional)
    notional = d_price * d_amount
    return notional >= d_min


def calculate_fee(
    notional: Union[Decimal, float, str],
    fee_rate: Union[Decimal, float, str]
) -> Decimal:
    """Calculates exchange trading fee given total notional and fee rate (e.g., 0.001 for 0.1%)."""
    d_notional = to_decimal(notional)
    d_fee_rate = to_decimal(fee_rate)
    return (d_notional * d_fee_rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def apply_slippage(
    price: Union[Decimal, float, str],
    slippage_pct: Union[Decimal, float, str],
    side: Union[OrderSide, str]
) -> Decimal:
    """
    Applies realistic slippage to execution price.
    BUY orders slip upward (+).
    SELL orders slip downward (-).
    """
    d_price = to_decimal(price)
    d_slip = to_decimal(slippage_pct) / Decimal("100")

    if side == OrderSide.BUY or str(side).lower() == "buy":
        return d_price * (Decimal("1") + d_slip)
    else:
        return d_price * (Decimal("1") - d_slip)


def calculate_pnl(
    entry_price: Union[Decimal, float, str],
    exit_price: Union[Decimal, float, str],
    amount: Union[Decimal, float, str],
    side: Union[OrderSide, str]
) -> Decimal:
    """Calculates raw gross PnL in quote currency."""
    d_entry = to_decimal(entry_price)
    d_exit = to_decimal(exit_price)
    d_amount = to_decimal(amount)

    if side == OrderSide.BUY or str(side).lower() == "buy":
        return (d_exit - d_entry) * d_amount
    else:
        return (d_entry - d_exit) * d_amount
