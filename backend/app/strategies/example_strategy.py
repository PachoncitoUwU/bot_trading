"""Example Trend & Momentum Strategy demonstrating BaseStrategy implementation."""
from decimal import Decimal
from typing import Any, Dict, List
from app.core.constants import SignalType
from app.core.decimal_math import to_decimal
from app.strategies.base_strategy import BaseStrategy, StrategySignal


class TrendMomentumStrategy(BaseStrategy):
    """
    Sample strategy using EMA Cross + RSI threshold rules.
    Demonstrates parameterization and deterministic signal emission.
    """

    def __init__(self, symbols: List[str], timeframe: str = "1h", params: Dict[str, Any] = None):
        default_params = {
            "fast_period": 9,
            "slow_period": 21,
            "rsi_buy_max": 65,
            "rsi_sell_min": 75,
            "sl_pct": Decimal("1.5"),
            "tp_pct": Decimal("3.0")
        }
        if params:
            default_params.update(params)
        super().__init__(name="TrendMomentum_v1", symbols=symbols, timeframe=timeframe, params=default_params)

    def _calculate_sma(self, closes: List[Decimal], period: int) -> Decimal:
        if len(closes) < period:
            return closes[-1]
        subset = closes[-period:]
        return sum(subset) / Decimal(str(period))

    def generate_signals(self, market_data: Dict[str, Any], open_positions: Dict[str, Any]) -> List[StrategySignal]:
        signals = []

        for symbol in self.symbols:
            candles = market_data.get(symbol, [])
            if len(candles) < self.params["slow_period"] + 2:
                continue

            # Extract closes
            closes = [to_decimal(c[4]) for c in candles]
            current_price = closes[-1]
            prev_price = closes[-2]

            fast_ma = self._calculate_sma(closes, self.params["fast_period"])
            slow_ma = self._calculate_sma(closes, self.params["slow_period"])
            prev_fast_ma = self._calculate_sma(closes[:-1], self.params["fast_period"])
            prev_slow_ma = self._calculate_sma(closes[:-1], self.params["slow_period"])

            is_in_position = symbol in open_positions

            # Bullish Crossover: Fast MA crosses above Slow MA
            if not is_in_position and prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
                sl_distance = current_price * (self.params["sl_pct"] / Decimal("100"))
                tp_distance = current_price * (self.params["tp_pct"] / Decimal("100"))
                
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        price=current_price,
                        stop_loss=current_price - sl_distance,
                        take_profit=current_price + tp_distance,
                        pattern_name="BULLISH_MA_CROSS",
                        reason="Fast MA crossed above Slow MA with upward momentum."
                    )
                )

            # Bearish Exit Crossover: Fast MA crosses below Slow MA
            elif is_in_position and prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        price=current_price,
                        pattern_name="BEARISH_MA_CROSS",
                        reason="Fast MA crossed below Slow MA. Closing long position."
                    )
                )

        return signals
