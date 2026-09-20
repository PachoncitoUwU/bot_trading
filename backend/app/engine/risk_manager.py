"""Risk Manager with Drawdown Limits, Exposure Caps, Partial Fills, and Kill Switch."""
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.constants import OrderSide, OrderStatus, OrderType
from app.core.decimal_math import (
    to_decimal,
    round_to_step_size,
    round_to_tick_size,
    validate_min_notional
)
from app.core.logger import logger
from app.engine.circuit_breaker import CircuitBreaker
from app.exchange.symbol_rules import symbol_rules_cache


@dataclass
class PositionRiskState:
    symbol: str
    target_amount: Decimal
    filled_amount: Decimal
    remaining_amount: Decimal
    avg_entry_price: Decimal
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    allocated_notional: Decimal

    @property
    def entry_price(self) -> Decimal:
        return self.avg_entry_price


class RiskManager:
    """
    Institutional Risk Manager.
    Enforces daily loss limits, aggregate exposure, position sizing, and partial fill reconciliation.
    """

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        max_daily_drawdown_pct: Optional[Decimal] = None,
        max_account_exposure_pct: Optional[Decimal] = None,
        max_risk_per_trade_pct: Optional[Decimal] = None
    ):
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            max_consecutive_errors=settings.CIRCUIT_BREAKER_MAX_ERRORS
        )
        self.max_daily_drawdown_pct = max_daily_drawdown_pct or settings.MAX_DAILY_DRAWDOWN_PCT
        self.max_account_exposure_pct = max_account_exposure_pct or settings.MAX_ACCOUNT_EXPOSURE_PCT
        self.max_risk_per_trade_pct = max_risk_per_trade_pct or settings.MAX_RISK_PER_TRADE_PCT

        # Daily Drawdown Tracker
        self.current_trading_day: date = datetime.utcnow().date()
        self.daily_starting_equity: Decimal = Decimal("0")
        self.daily_high_watermark: Decimal = Decimal("0")
        self.is_daily_drawdown_locked: bool = False

        # Active Positions Tracked by Risk Manager
        self.active_positions: Dict[str, PositionRiskState] = {}

    def update_daily_equity(self, current_equity: Decimal) -> Tuple[bool, str]:
        """
        Updates daily high-water mark and verifies drawdown limit.
        Returns: (is_safe, message)
        """
        today = datetime.utcnow().date()
        if today != self.current_trading_day or self.daily_starting_equity == Decimal("0"):
            self.current_trading_day = today
            self.daily_starting_equity = current_equity
            self.daily_high_watermark = current_equity
            self.is_daily_drawdown_locked = False
            logger.info(f"[RISK MANAGER] New trading day initialized. Starting equity: ${current_equity}")

        if current_equity > self.daily_high_watermark:
            self.daily_high_watermark = current_equity

        if self.daily_high_watermark > Decimal("0"):
            drawdown_pct = ((self.daily_high_watermark - current_equity) / self.daily_high_watermark) * Decimal("100")
            if drawdown_pct >= self.max_daily_drawdown_pct:
                self.is_daily_drawdown_locked = True
                msg = f"[ALERT: DAILY DRAWDOWN LIMIT HIT] Drawdown: {drawdown_pct:.2f}% (Limit: {self.max_daily_drawdown_pct}%). New entries LOCKED."
                logger.error(msg)
                return False, msg

        return True, "Equity within safe parameters."

    def reset_daily_limits(self, current_equity: Decimal) -> None:
        """Manually resets the daily drawdown baseline, high-water mark, and clears all lockouts."""
        if current_equity > Decimal("0"):
            self.daily_starting_equity = current_equity
            self.daily_high_watermark = current_equity
        self.is_daily_drawdown_locked = False
        if hasattr(self, "circuit_breaker"):
            self.circuit_breaker.manual_reset()
        logger.info(f"[RISK MANAGER] Límites de riesgo reiniciados manualmente. Nueva línea base: ${current_equity:.2f} USD")

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Optional[Decimal],
        total_account_equity: Decimal,
        available_cash: Decimal
    ) -> Tuple[bool, Decimal, str]:
        """
        Calculates safe position size considering risk per trade, minNotional, and max exposure.
        """
        # 1. Circuit Breaker Check
        if not self.circuit_breaker.can_trade():
            return False, Decimal("0"), f"Circuit breaker TRIPPED: {self.circuit_breaker.trip_reason}"

        # 2. Daily Drawdown Lock Check
        if self.is_daily_drawdown_locked:
            return False, Decimal("0"), "Trading locked due to daily drawdown limit."

        # 3. Aggregate Exposure Check
        current_total_exposure = sum([p.allocated_notional for p in self.active_positions.values()], Decimal("0"))
        max_allowed_exposure = total_account_equity * (self.max_account_exposure_pct / Decimal("100"))
        
        if current_total_exposure >= max_allowed_exposure:
            return False, Decimal("0"), f"Aggregate exposure cap reached: ${current_total_exposure:.2f} / ${max_allowed_exposure:.2f}"

        # 4. Symbol Rules
        rules = symbol_rules_cache.get_rules(symbol)
        step_size = rules.step_size if rules else Decimal("0.00001")
        min_notional = rules.min_notional if rules else Decimal("5.0")
        tick_size = rules.tick_size if rules else Decimal("0.01")

        # 5. Position Sizing by Risk Per Trade
        if stop_loss and stop_loss > Decimal("0") and stop_loss < entry_price:
            risk_amount_usd = total_account_equity * (self.max_risk_per_trade_pct / Decimal("100"))
            sl_distance_per_unit = entry_price - stop_loss
            target_amount = risk_amount_usd / sl_distance_per_unit
        else:
            # Fallback allocation if no SL specified (e.g. 5% of cash)
            target_amount = (available_cash * Decimal("0.05")) / entry_price

        # Cap by available remaining exposure and cash
        remaining_exposure_room = max_allowed_exposure - current_total_exposure
        max_notional_by_cash = min(available_cash, remaining_exposure_room)
        target_amount = min(target_amount, max_notional_by_cash / entry_price)

        # Round down to step size
        safe_amount = round_to_step_size(target_amount, step_size)
        notional = safe_amount * entry_price

        if not validate_min_notional(entry_price, safe_amount, min_notional):
            return False, Decimal("0"), f"Calculated order ${notional:.2f} below minNotional (${min_notional:.2f})"

        return True, safe_amount, "Position size validated successfully."

    def handle_partial_fill(
        self,
        symbol: str,
        fill_amount: Decimal,
        fill_price: Decimal,
        total_target_amount: Decimal,
        stop_loss: Optional[Decimal],
        take_profit: Optional[Decimal]
    ) -> PositionRiskState:
        """
        Updates internal risk state when an order fills partially or completely.
        Recalculates weighted average entry price and remaining risk exposure.
        """
        existing = self.active_positions.get(symbol)

        if not existing:
            # First fill of new position
            remaining = total_target_amount - fill_amount
            state = PositionRiskState(
                symbol=symbol,
                target_amount=total_target_amount,
                filled_amount=fill_amount,
                remaining_amount=remaining,
                avg_entry_price=fill_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                allocated_notional=fill_amount * fill_price
            )
            self.active_positions[symbol] = state
            logger.info(f"[RISK MANAGER] Partial Fill registered for {symbol}: {fill_amount}/{total_target_amount} @ ${fill_price}")
            return state
        else:
            # Subsequent partial fill: update weighted average price
            total_filled = existing.filled_amount + fill_amount
            new_avg_price = ((existing.avg_entry_price * existing.filled_amount) + (fill_price * fill_amount)) / total_filled
            existing.filled_amount = total_filled
            existing.remaining_amount = max(Decimal("0"), existing.target_amount - total_filled)
            existing.avg_entry_price = new_avg_price
            existing.allocated_notional = total_filled * new_avg_price
            logger.info(f"[RISK MANAGER] Fill updated for {symbol}: Total Filled={total_filled} @ AvgPrice=${new_avg_price:.4f}")
            return existing

    def close_position(self, symbol: str) -> Optional[PositionRiskState]:
        """Removes a position from active risk tracking upon closure."""
        return self.active_positions.pop(symbol, None)
