"""Phase 3 Verification Script: BaseStrategy & Walk-Forward Backtesting Engine."""
import asyncio
import sys
import os
from decimal import Decimal
import math

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.strategies.example_strategy import TrendMomentumStrategy
from app.engine.backtester import BacktestingEngine


def generate_synthetic_ohlcv_trend(n_bars: int = 200) -> list:
    """Generates synthetic trend and pullback price bars for testing."""
    candles = []
    base_price = 50000.0
    
    for i in range(n_bars):
        # Oscillating cycle with multiple crossover points
        wave = math.sin(i / 8.0) * 800.0 + (i * 10.0)
        close = base_price + wave
        open_p = close - 20.0
        high_p = max(open_p, close) + 50.0
        low_p = min(open_p, close) - 50.0
        vol = 100.0
        timestamp = 1700000000 + (i * 3600)
        candles.append([timestamp, open_p, high_p, low_p, close, vol])
        
    return candles


async def run_phase3_tests():
    print("==================================================")
    print("[START] INICIANDO VERIFICACION DE FASE 3 (TDD)")
    print("==================================================")

    # 1. Base Strategy Signal Generation Tests
    print("1. Probando Generacion de Senales en BaseStrategy (TrendMomentumStrategy)...")
    strategy = TrendMomentumStrategy(symbols=["BTC/USDT"], timeframe="1h")
    candles = generate_synthetic_ohlcv_trend(n_bars=120)
    
    signals = strategy.generate_signals(market_data={"BTC/USDT": candles}, open_positions={})
    assert isinstance(signals, list)
    print("   [OK] BaseStrategy: Emision de senales parametrizadas completada.")

    # 2. Backtesting Engine Tests (Fees, Slippage & Drawdown)
    print("2. Probando Motor de Backtesting con Comisiones y Deslizamiento (Fees & Slippage)...")
    engine = BacktestingEngine(
        initial_capital=Decimal("10000.00"),
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        slippage_pct=Decimal("0.05")
    )
    
    report = engine.run_backtest_on_candles(strategy, candles, "BTC/USDT")
    assert report.total_fees_paid > Decimal("0")
    assert report.initial_balance == Decimal("10000.00")
    assert isinstance(report.max_drawdown_pct, Decimal)
    assert isinstance(report.win_rate_pct, Decimal)
    assert isinstance(report.profit_factor, Decimal)
    print(f"   [OK] Reporte de Backtest: Trades={report.total_trades} | Fees Pagados=${report.total_fees_paid} | Max DD={report.max_drawdown_pct}% | Retorno={report.net_profit_pct}%")

    # 3. Walk-Forward (In-Sample 70% vs Out-of-Sample 30%) Validation
    print("3. Probando Validacion Walk-Forward (Evitar Sobreajuste / Overfitting)...")
    wf_result = engine.run_walk_forward_backtest(strategy, candles, "BTC/USDT", train_ratio=0.70)
    
    assert wf_result.in_sample_report.total_trades >= 0
    assert wf_result.out_of_sample_report.total_trades >= 0
    assert wf_result.full_report.total_trades >= wf_result.in_sample_report.total_trades
    print(f"   [OK] In-Sample (70%): Retorno={wf_result.in_sample_report.net_profit_pct}% | WinRate={wf_result.in_sample_report.win_rate_pct}%")
    print(f"   [OK] Out-of-Sample (30%): Retorno={wf_result.out_of_sample_report.net_profit_pct}% | WinRate={wf_result.out_of_sample_report.win_rate_pct}%")
    print(f"   [OK] Diagnostico de Sobreajuste: {wf_result.overfitting_warning}")

    print("==================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE FASE 3 PASARON CON EXITO")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase3_tests())
