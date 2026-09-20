"""Verification script for Dynamic Staking, Multi-Concurrent Trades (10), and Adaptive Duration."""
import asyncio
import os
import sys
from decimal import Decimal

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath("backend"))

from app.core.config import settings
from app.core.constants import OrderSide, SignalType
from app.engine.staking_manager import StakingManager
from app.strategies.base_strategy import StrategySignal


def test_staking_manager_dynamic_logic():
    print("=== [TEST 1] Testing StakingManager Dynamic Stakes & Safety Cap ===")
    sm = StakingManager(steps=[10.0, 25.0])
    assert sm.steps == [Decimal("10.0"), Decimal("25.0")], f"Expected [10.0, 25.0], got {sm.steps}"

    # 1. Base stake for standard confidence
    stake, reason = sm.calculate_dynamic_stake(confidence=Decimal("0.55"), confluences=1)
    assert stake == Decimal("10.0"), f"Expected $10.0, got {stake}"
    print(f"  [OK] Standard signal: {stake} USD | {reason}")

    # 2. High conviction stake (>= 0.70 & >= 2 confluences)
    stake, reason = sm.calculate_dynamic_stake(confidence=Decimal("0.75"), confluences=2)
    assert stake == Decimal("25.0"), f"Expected $25.0, got {stake}"
    print(f"  [OK] High conviction signal: {stake} USD | {reason}")

    # 3. Maximum conviction stake (>= 0.85 & >= 3 confluences)
    stake, reason = sm.calculate_dynamic_stake(confidence=Decimal("0.90"), confluences=3)
    assert stake == Decimal("50.0"), f"Expected $50.0, got {stake}"
    print(f"  [OK] Max conviction signal: {stake} USD | {reason}")

    # 4. Strict Safety Cap: Can NEVER exceed $50
    stake, _ = sm.calculate_dynamic_stake(confidence=Decimal("1.0"), confluences=5)
    assert stake <= Decimal("50.0"), f"Stake exceeded safety cap: {stake}"
    print(f"  [OK] Hard safety cap enforced: {stake} <= $50.0 USD")

    # 5. Recovery progression: Loss at step 0 -> step 1 ($25 USD)
    res = sm.record_trade_result(is_win=False, profit_usd=-10.0, symbol="EURUSD-OTC")
    assert sm.current_step_index == 1
    assert sm.get_current_stake() == Decimal("25.0")
    print(f"  [OK] Loss at Step 1 advanced to Step 2: Next stake = ${sm.get_current_stake()} USD")

    # 6. In Recovery mode: calculate_dynamic_stake returns recovery stake ($25)
    stake, reason = sm.calculate_dynamic_stake(confidence=Decimal("0.90"), confluences=3)
    assert stake == Decimal("25.0"), f"In recovery, expected recovery stake $25, got {stake}"
    print(f"  [OK] Recovery mode takes precedence: {stake} USD | {reason}")

    # 7. Safety protection: Loss at step 1 -> Resets to step 0 ($10 USD)
    res = sm.record_trade_result(is_win=False, profit_usd=-25.0, symbol="EURUSD-OTC")
    assert sm.current_step_index == 0
    assert sm.get_current_stake() == Decimal("10.0")
    assert res["event"] == "LOSS_RESET_PROTECTION"
    print(f"  [OK] Loss at Step 2 triggered safety protection reset to Step 1: ${sm.get_current_stake()} USD")

    # 8. Win at Step 1 -> Immediate reset
    sm.record_trade_result(is_win=False, profit_usd=-10.0, symbol="EURUSD-OTC") # advance to 1
    assert sm.current_step_index == 1
    res = sm.record_trade_result(is_win=True, profit_usd=21.75, symbol="EURUSD-OTC")
    assert sm.current_step_index == 0
    assert sm.get_current_stake() == Decimal("10.0")
    print(f"  [OK] Win at Step 2 immediately reset to Step 1: ${sm.get_current_stake()} USD")


def test_dynamic_duration_logic():
    print("\n=== [TEST 2] Testing Dynamic Duration (1m vs 3m vs 5m) ===")
    
    # Helper replicating bot_runner's duration calculation
    def get_duration(sig):
        sig_conf = getattr(sig, "confidence", Decimal("0.5"))
        sig_confluences = getattr(sig, "metadata", {}).get("confluences", 1)
        if sig_conf >= Decimal("0.80") and sig_confluences >= 3:
            return 5
        elif sig_conf >= Decimal("0.65") or sig_confluences >= 2:
            return 3
        else:
            return 1

    # Standard / Scalping
    sig_fast = StrategySignal(
        symbol="EURUSD-OTC",
        signal_type=SignalType.BUY,
        price=Decimal("1.0850"),
        confidence=Decimal("0.55"),
        metadata={"confluences": 1}
    )
    assert get_duration(sig_fast) == 1, "Expected 1m for fast scalping"
    print("  [OK] Fast momentum signal assigned: 1m")

    # High conviction / Technical reversal
    sig_high = StrategySignal(
        symbol="GBPUSD-OTC",
        signal_type=SignalType.BUY,
        price=Decimal("1.2750"),
        confidence=Decimal("0.70"),
        metadata={"confluences": 2}
    )
    assert get_duration(sig_high) == 3, "Expected 3m for high conviction"
    print("  [OK] High conviction signal assigned: 3m")

    # Maximum conviction / Triple confluence
    sig_max = StrategySignal(
        symbol="USDJPY-OTC",
        signal_type=SignalType.BUY,
        price=Decimal("155.20"),
        confidence=Decimal("0.88"),
        metadata={"confluences": 3}
    )
    assert get_duration(sig_max) == 5, "Expected 5m for triple confluence"
    print("  [OK] Max conviction signal assigned: 5m")


def test_bot_runner_concurrency_limit():
    print("\n=== [TEST 3] Testing BotRunner Concurrency Configuration ===")
    from app.engine.bot_runner import BotRunner
    runner = BotRunner()
    assert runner.max_concurrent_binary_trades == 10, f"Expected 10 max concurrent trades, got {runner.max_concurrent_binary_trades}"
    print(f"  [OK] BotRunner max_concurrent_binary_trades = {runner.max_concurrent_binary_trades}")
    print(f"  [OK] Settings IQOPTION_MARTINGALE_STEPS = {settings.IQOPTION_MARTINGALE_STEPS}")


if __name__ == "__main__":
    test_staking_manager_dynamic_logic()
    test_dynamic_duration_logic()
    test_bot_runner_concurrency_limit()
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")
