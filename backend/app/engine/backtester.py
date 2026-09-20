"""Walk-Forward Backtesting Engine for Strategy Validation with Realistic Fees & Slippage."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.core.constants import OrderSide, SignalType
from app.core.decimal_math import (
    to_decimal,
    apply_slippage,
    calculate_fee,
    calculate_pnl
)
from app.strategies.base_strategy import BaseStrategy


@dataclass
class BacktestTrade:
    symbol: str
    entry_time: Any
    exit_time: Any
    entry_price: Decimal
    exit_price: Decimal
    amount: Decimal
    fee_paid: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    exit_reason: str  # "TAKE_PROFIT" | "STOP_LOSS" | "SIGNAL_CLOSE" | "END_OF_DATA"


@dataclass
class PerformanceReport:
    segment_name: str  # "IN_SAMPLE" | "OUT_OF_SAMPLE" | "FULL_PERIOD"
    initial_balance: Decimal
    final_balance: Decimal
    net_profit_pct: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: Decimal
    profit_factor: Decimal
    max_drawdown_pct: Decimal
    total_fees_paid: Decimal
    trades: List[BacktestTrade] = field(default_factory=list)


@dataclass
class WalkForwardResult:
    in_sample_report: PerformanceReport
    out_of_sample_report: PerformanceReport
    full_report: PerformanceReport
    is_overfitted: bool
    overfitting_warning: str = ""


class BacktestingEngine:
    """
    Backtesting Engine with Walk-Forward out-of-sample testing,
    slippage simulation, fee deductions, and peak-to-trough drawdown calculation.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("10000.00"),
        maker_fee_rate: Decimal = Decimal("0.001"),  # 0.1%
        taker_fee_rate: Decimal = Decimal("0.001"),  # 0.1%
        slippage_pct: Decimal = Decimal("0.05"),     # 0.05% slippage
        position_size_pct: Decimal = Decimal("95.0") # Allocate 95% of available cash per trade
    ):
        self.initial_capital = initial_capital
        self.maker_fee_rate = maker_fee_rate
        self.taker_fee_rate = taker_fee_rate
        self.slippage_pct = slippage_pct
        self.position_size_pct = position_size_pct

    def run_backtest_on_candles(
        self,
        strategy: BaseStrategy,
        candles: List[List[Any]],
        symbol: str,
        segment_name: str = "FULL_PERIOD"
    ) -> PerformanceReport:
        """Runs sequential bar-by-bar backtest over a set of OHLCV candles."""
        cash = self.initial_capital
        peak_balance = self.initial_capital
        max_drawdown_pct = Decimal("0")
        total_fees = Decimal("0")
        trades: List[BacktestTrade] = []

        open_position: Optional[Dict[str, Any]] = None

        # Minimum required lookback bars
        min_bars = 25
        if len(candles) < min_bars:
            return PerformanceReport(
                segment_name=segment_name,
                initial_balance=self.initial_capital,
                final_balance=self.initial_capital,
                net_profit_pct=Decimal("0"),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=Decimal("0"),
                profit_factor=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                total_fees_paid=Decimal("0")
            )

        for i in range(min_bars, len(candles)):
            current_bar = candles[i]
            bar_time, bar_open, bar_high, bar_low, bar_close, bar_vol = current_bar
            bar_high_dec = to_decimal(bar_high)
            bar_low_dec = to_decimal(bar_low)
            bar_close_dec = to_decimal(bar_close)

            # 1. Check Stop Loss / Take Profit on active position
            if open_position:
                sl = open_position.get("stop_loss")
                tp = open_position.get("take_profit")
                exit_price = None
                exit_reason = ""

                # Hit Stop Loss
                if sl and bar_low_dec <= sl:
                    exit_price = apply_slippage(sl, self.slippage_pct, OrderSide.SELL)
                    exit_reason = "STOP_LOSS"
                # Hit Take Profit
                elif tp and bar_high_dec >= tp:
                    exit_price = apply_slippage(tp, self.slippage_pct, OrderSide.SELL)
                    exit_reason = "TAKE_PROFIT"

                if exit_price:
                    trade_amount = open_position["amount"]
                    gross_pnl = calculate_pnl(open_position["entry_price"], exit_price, trade_amount, OrderSide.BUY)
                    exit_notional = exit_price * trade_amount
                    exit_fee = calculate_fee(exit_notional, self.taker_fee_rate)
                    total_trade_fees = open_position["entry_fee"] + exit_fee
                    net_pnl = gross_pnl - total_trade_fees

                    cash += (exit_notional - exit_fee)
                    total_fees += exit_fee

                    trades.append(BacktestTrade(
                        symbol=symbol,
                        entry_time=open_position["entry_time"],
                        exit_time=bar_time,
                        entry_price=open_position["entry_price"],
                        exit_price=exit_price,
                        amount=trade_amount,
                        fee_paid=total_trade_fees,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        exit_reason=exit_reason
                    ))
                    open_position = None

            # 2. Feed historical slice to strategy to evaluate signals
            slice_candles = candles[:i + 1]
            market_data = {symbol: slice_candles}
            current_positions = {symbol: open_position} if open_position else {}
            signals = strategy.generate_signals(market_data, current_positions)

            for sig in signals:
                if sig.signal_type == SignalType.BUY and not open_position:
                    # Execute Buy with slippage and fees
                    entry_price = apply_slippage(sig.price, self.slippage_pct, OrderSide.BUY)
                    allocated_cash = cash * (self.position_size_pct / Decimal("100"))
                    if allocated_cash > Decimal("5.0"):
                        entry_fee_est = calculate_fee(allocated_cash, self.taker_fee_rate)
                        trade_amount = (allocated_cash - entry_fee_est) / entry_price
                        entry_notional = entry_price * trade_amount
                        entry_fee = calculate_fee(entry_notional, self.taker_fee_rate)
                        
                        cash -= (entry_notional + entry_fee)
                        total_fees += entry_fee

                        open_position = {
                            "symbol": symbol,
                            "entry_time": bar_time,
                            "entry_price": entry_price,
                            "amount": trade_amount,
                            "entry_fee": entry_fee,
                            "stop_loss": sig.stop_loss,
                            "take_profit": sig.take_profit
                        }

                elif sig.signal_type == SignalType.SELL and open_position:
                    # Close position via strategy signal
                    exit_price = apply_slippage(sig.price, self.slippage_pct, OrderSide.SELL)
                    trade_amount = open_position["amount"]
                    gross_pnl = calculate_pnl(open_position["entry_price"], exit_price, trade_amount, OrderSide.BUY)
                    exit_notional = exit_price * trade_amount
                    exit_fee = calculate_fee(exit_notional, self.taker_fee_rate)
                    total_trade_fees = open_position["entry_fee"] + exit_fee
                    net_pnl = gross_pnl - total_trade_fees

                    cash += (exit_notional - exit_fee)
                    total_fees += exit_fee

                    trades.append(BacktestTrade(
                        symbol=symbol,
                        entry_time=open_position["entry_time"],
                        exit_time=bar_time,
                        entry_price=open_position["entry_price"],
                        exit_price=exit_price,
                        amount=trade_amount,
                        fee_paid=total_trade_fees,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        exit_reason="SIGNAL_CLOSE"
                    ))
                    open_position = None

            # Track Drawdown
            current_portfolio_value = cash
            if open_position:
                current_portfolio_value += (open_position["amount"] * bar_close_dec)

            if current_portfolio_value > peak_balance:
                peak_balance = current_portfolio_value
            elif peak_balance > Decimal("0"):
                drawdown = ((peak_balance - current_portfolio_value) / peak_balance) * Decimal("100")
                if drawdown > max_drawdown_pct:
                    max_drawdown_pct = drawdown

        # Close open position at end of backtest period
        if open_position:
            last_bar = candles[-1]
            exit_price = to_decimal(last_bar[4])
            trade_amount = open_position["amount"]
            gross_pnl = calculate_pnl(open_position["entry_price"], exit_price, trade_amount, OrderSide.BUY)
            exit_notional = exit_price * trade_amount
            exit_fee = calculate_fee(exit_notional, self.taker_fee_rate)
            total_trade_fees = open_position["entry_fee"] + exit_fee
            net_pnl = gross_pnl - total_trade_fees

            cash += (exit_notional - exit_fee)
            total_fees += exit_fee

            trades.append(BacktestTrade(
                symbol=symbol,
                entry_time=open_position["entry_time"],
                exit_time=last_bar[0],
                entry_price=open_position["entry_price"],
                exit_price=exit_price,
                amount=trade_amount,
                fee_paid=total_trade_fees,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                exit_reason="END_OF_DATA"
            ))

        # Calculate Performance Metrics
        final_balance = cash
        net_profit_pct = ((final_balance - self.initial_capital) / self.initial_capital) * Decimal("100")
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.net_pnl > Decimal("0")])
        losing_trades = len([t for t in trades if t.net_pnl < Decimal("0")])
        win_rate_pct = (Decimal(str(winning_trades)) / Decimal(str(total_trades)) * Decimal("100")) if total_trades > 0 else Decimal("0")

        gross_profits = sum([t.net_pnl for t in trades if t.net_pnl > 0], Decimal("0"))
        gross_losses = abs(sum([t.net_pnl for t in trades if t.net_pnl < 0], Decimal("0")))
        profit_factor = (gross_profits / gross_losses) if gross_losses > Decimal("0") else (Decimal("99.9") if gross_profits > 0 else Decimal("0"))

        return PerformanceReport(
            segment_name=segment_name,
            initial_balance=self.initial_capital,
            final_balance=final_balance.quantize(Decimal("0.01")),
            net_profit_pct=net_profit_pct.quantize(Decimal("0.01")),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate_pct.quantize(Decimal("0.1")),
            profit_factor=profit_factor.quantize(Decimal("0.01")),
            max_drawdown_pct=max_drawdown_pct.quantize(Decimal("0.01")),
            total_fees_paid=total_fees.quantize(Decimal("0.01")),
            trades=trades
        )

    def run_walk_forward_backtest(
        self,
        strategy: BaseStrategy,
        candles: List[List[Any]],
        symbol: str,
        train_ratio: float = 0.70  # 70% In-Sample (Train), 30% Out-of-Sample (Test)
    ) -> WalkForwardResult:
        """
        Splits dataset into in-sample and out-of-sample sets.
        Detects if a strategy is overfitted to the past.
        """
        split_idx = int(len(candles) * train_ratio)
        in_sample_candles = candles[:split_idx]
        out_of_sample_candles = candles[split_idx:]

        # Run on in-sample
        in_sample_report = self.run_backtest_on_candles(strategy, in_sample_candles, symbol, segment_name="IN_SAMPLE (Train 70%)")
        
        # Run on out-of-sample
        out_of_sample_report = self.run_backtest_on_candles(strategy, out_of_sample_candles, symbol, segment_name="OUT_OF_SAMPLE (Test 30%)")
        
        # Run full period
        full_report = self.run_backtest_on_candles(strategy, candles, symbol, segment_name="FULL_PERIOD")

        # Overfitting check: Did Out-of-Sample performance collapse compared to In-Sample?
        is_overfitted = False
        warning = "Strategy passed walk-forward validation."

        if in_sample_report.net_profit_pct > Decimal("5.0") and out_of_sample_report.net_profit_pct < Decimal("-3.0"):
            is_overfitted = True
            warning = "⚠️ OVERFITTING DETECTED: In-Sample was profitable but Out-of-Sample lost money."

        return WalkForwardResult(
            in_sample_report=in_sample_report,
            out_of_sample_report=out_of_sample_report,
            full_report=full_report,
            is_overfitted=is_overfitted,
            overfitting_warning=warning
        )
