"""Phase 4 Verification Script: RiskManager, CircuitBreaker & Partial Fills."""
import asyncio
import sys
import os
from decimal import Decimal

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.constants import CircuitBreakerStatus
from app.engine.circuit_breaker import CircuitBreaker
from app.engine.risk_manager import RiskManager
from app.exchange.symbol_rules import symbol_rules_cache, SymbolRules


async def run_phase4_tests():
    print("==================================================")
    print("[START] INICIANDO VERIFICACION DE FASE 4 (TDD)")
    print("==================================================")

    # 1. Circuit Breaker Tests
    print("1. Probando Circuit Breaker (Errores consecutivos y parada de emergencia)...")
    cb = CircuitBreaker(max_consecutive_errors=3)
    assert cb.can_trade() is True
    
    cb.record_error("Connection timeout 1")
    assert cb.can_trade() is True
    
    cb.record_error("Connection timeout 2")
    assert cb.can_trade() is True
    
    # 3rd error must TRIP the breaker
    is_tripped = cb.record_error("Connection timeout 3")
    assert is_tripped is True
    assert cb.can_trade() is False
    assert cb.status == CircuitBreakerStatus.TRIPPED
    print("   [OK] Circuit Breaker: Auto-disparo tras 3 errores consecutivos comprobado.")

    # Reset
    cb.manual_reset()
    assert cb.can_trade() is True
    print("   [OK] Circuit Breaker: Reset manual funcional.")

    # Setup symbol rules for sizing test
    symbol_rules_cache._rules["BTC/USDT"] = SymbolRules(
        symbol="BTC/USDT",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        min_amount=Decimal("0.001"),
        max_amount=Decimal("100.0"),
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001")
    )

    # 2. Risk Manager: Position Sizing & Aggregate Exposure
    print("2. Probando RiskManager: Dimensionamiento por riesgo (1%) y Cap de Exposicion (20%)...")
    rm = RiskManager(
        circuit_breaker=cb,
        max_daily_drawdown_pct=Decimal("3.0"),
        max_account_exposure_pct=Decimal("20.0"),
        max_risk_per_trade_pct=Decimal("1.0")
    )
    
    # Account Equity: $10,000 | Available Cash: $10,000
    # Entry: $50,000 | Stop Loss: $49,000 ($1,000 distance = 2% SL)
    # Risk 1% of $10,000 = $100 risk.
    # Target Amount = $100 / $1,000 = 0.100 BTC. Notional = $5,000 (within 20% / $2,000 max exposure limit -> capped at $2,000 = 0.040 BTC)
    is_valid, size, reason = rm.calculate_position_size(
        symbol="BTC/USDT",
        entry_price=Decimal("50000.00"),
        stop_loss=Decimal("49000.00"),
        total_account_equity=Decimal("10000.00"),
        available_cash=Decimal("10000.00")
    )
    assert is_valid is True
    # Max exposure 20% of 10k is $2000 / 50k = 0.040 BTC
    assert size == Decimal("0.040")
    print(f"   [OK] Dimensionamiento Seguro: Tamano calculado={size} BTC (Alineado con Exposure Cap del 20%).")

    # 3. Partial Fill Tracker Tests
    print("3. Probando Rastreador de Llenados Parciales (Partial Fills)...")
    # Order of 0.040 BTC fills 0.020 @ 50,000 first
    state = rm.handle_partial_fill(
        symbol="BTC/USDT",
        fill_amount=Decimal("0.020"),
        fill_price=Decimal("50000.00"),
        total_target_amount=Decimal("0.040"),
        stop_loss=Decimal("49000.00"),
        take_profit=Decimal("52000.00")
    )
    assert state.filled_amount == Decimal("0.020")
    assert state.remaining_amount == Decimal("0.020")
    assert state.avg_entry_price == Decimal("50000.00")

    # Second partial fill: remaining 0.020 fills @ 50,200 (weighted avg: 50,100)
    updated_state = rm.handle_partial_fill(
        symbol="BTC/USDT",
        fill_amount=Decimal("0.020"),
        fill_price=Decimal("50200.00"),
        total_target_amount=Decimal("0.040"),
        stop_loss=Decimal("49000.00"),
        take_profit=Decimal("52000.00")
    )
    assert updated_state.filled_amount == Decimal("0.040")
    assert updated_state.remaining_amount == Decimal("0.000")
    assert updated_state.avg_entry_price == Decimal("50100.00")
    print("   [OK] Partial Fills: Precio promedio ponderado ($50,100) y saldo remanente exactos.")

    # 4. Daily Drawdown Limit Tests
    print("4. Probando Limite de Drawdown Diario (3.0% Max Loss)...")
    rm.update_daily_equity(Decimal("10000.00"))
    # Drop to $9,650 (3.5% drawdown from peak $10,000)
    is_safe, msg = rm.update_daily_equity(Decimal("9650.00"))
    assert is_safe is False
    assert rm.is_daily_drawdown_locked is True

    # Check that new entries are immediately rejected
    can_open, _, block_msg = rm.calculate_position_size(
        symbol="BTC/USDT",
        entry_price=Decimal("50000.00"),
        stop_loss=Decimal("49000.00"),
        total_account_equity=Decimal("9650.00"),
        available_cash=Decimal("5000.00")
    )
    assert can_open is False
    print("   [OK] Limite de Perdida Diaria: Bot BLOQUEADO tras alcanzar -3.5% de Drawdown.")

    print("==================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE FASE 4 PASARON CON EXITO")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase4_tests())
