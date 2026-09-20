"""Standalone Phase 1 Verification Script (Zero extra dependencies)."""
import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.constants import BotMode, OrderSide, OrderStatus
from app.core.decimal_math import (
    to_decimal,
    round_to_step_size,
    round_to_tick_size,
    validate_min_notional,
    calculate_fee,
    apply_slippage,
    calculate_pnl
)
from app.core.rate_limiter import AsyncTokenBucketRateLimiter
from app.core.time_sync import TimeSyncManager
from decimal import Decimal


async def run_all_tests():
    print("==================================================")
    print("[START] INICIANDO VERIFICACION DE FASE 1 (TDD)")
    print("==================================================")

    # 1. Decimal Math Tests
    print("1. Probando Aritmetica Fija Decimal y Casos Limite...")
    assert to_decimal("0.000123") == Decimal("0.000123")
    assert round_to_step_size("0.12345", "0.001") == Decimal("0.123")
    assert round_to_step_size("0.12399", "0.001") == Decimal("0.123")
    assert round_to_step_size("1.000", "0.001") == Decimal("1.000")
    assert round_to_step_size("0.00099", "0.001") == Decimal("0.000")
    assert round_to_tick_size("65432.176", "0.01") == Decimal("65432.18")
    assert round_to_tick_size("100.50", "0.01") == Decimal("100.50")
    
    # Boundary min_notional ($4.999999 vs $5.00 vs $5.000001)
    min_notional = Decimal("5.00000000")
    assert validate_min_notional("50.00", "0.10", min_notional) is True
    assert validate_min_notional("49.99999", "0.10", min_notional) is False
    assert validate_min_notional("50.00001", "0.10", min_notional) is True
    
    # Bidirectional slippage
    buy_slip = apply_slippage("100.0", "0.5", OrderSide.BUY)
    sell_slip = apply_slippage("100.0", "0.5", OrderSide.SELL)
    assert buy_slip == Decimal("100.500") and buy_slip > Decimal("100.0")
    assert sell_slip == Decimal("99.500") and sell_slip < Decimal("100.0")

    assert calculate_fee("1000.00", "0.001") == Decimal("1.00000000")
    assert calculate_pnl("100", "110", "2", OrderSide.BUY) == Decimal("20")
    assert calculate_pnl("100", "90", "1", OrderSide.BUY) == Decimal("-10")
    print("   [OK] Aritmetica Decimal: 100% Precisa con Casos Limite Probados")

    # 2. Rate Limiter Tests
    print("2. Probando Token Bucket Rate Limiter...")
    limiter = AsyncTokenBucketRateLimiter(capacity=5.0, refill_rate=10.0)
    acquired = await limiter.acquire(weight=5.0)
    assert acquired is True
    assert limiter.get_current_tokens() < 1.0
    await asyncio.sleep(0.3)
    assert limiter.get_current_tokens() >= 2.0
    print("   [OK] Rate Limiter: Proteccion de IP y llamadas funcionando")

    # 3. Time Sync Tests
    print("3. Probando Sincronizador de Reloj (NTP / Exchange Drift)...")
    sync = TimeSyncManager(max_allowed_drift_ms=500)
    local_ms = sync.get_local_timestamp_ms()
    is_healthy, drift = sync.sync_with_server_time(local_ms + 150)
    assert is_healthy is True
    is_unhealthy, bad_drift = sync.sync_with_server_time(local_ms + 1200)
    assert is_unhealthy is False
    print("   [OK] Time Sync Manager: Deteccion y compensacion de desfasaje correcta")

    print("==================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE FASE 1 PASARON CON EXITO")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
