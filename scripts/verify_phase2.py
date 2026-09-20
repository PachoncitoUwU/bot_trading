"""Phase 2 Verification Script: CCXT Rules & Conservative State Reconciler."""
import asyncio
import sys
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.constants import BotMode
from app.exchange.symbol_rules import SymbolRulesCache
from app.exchange.ccxt_adapter import CCXTExchangeAdapter
from app.engine.state_reconciler import StateReconciler


async def run_phase2_tests():
    print("==================================================")
    print("[START] INICIANDO VERIFICACION DE FASE 2 (TDD)")
    print("==================================================")

    # 1. Symbol Rules Cache Tests
    print("1. Probando Parser de Reglas de Simbolos (tick_size, step_size, min_notional)...")
    cache = SymbolRulesCache()
    mock_market = {
        "symbol": "BTC/USDT",
        "precision": {"price": "0.01", "amount": "0.00001"},
        "limits": {
            "amount": {"min": 0.0001, "max": 1000},
            "cost": {"min": 5.0}
        },
        "maker": "0.001",
        "taker": "0.001"
    }
    rules = cache.parse_and_store_from_ccxt(mock_market)
    assert rules.symbol == "BTC/USDT"
    assert rules.tick_size == Decimal("0.01")
    assert rules.step_size == Decimal("0.00001")
    assert rules.min_notional == Decimal("5.0")
    assert rules.maker_fee_rate == Decimal("0.001")
    print("   [OK] SymbolRulesCache: Parseo y almacenamiento exacto.")

    # 2. CCXT Exchange Adapter Tests (Paper Mode)
    print("2. Probando CCXT Exchange Adapter en modo PAPER...")
    adapter = CCXTExchangeAdapter(exchange_id="binance", mode=BotMode.PAPER)
    balances = await adapter.fetch_balance()
    assert balances["USDT"] == Decimal("10000.00")
    print("   [OK] CCXT Adapter Paper Mode: Inicializacion y balance correcto.")

    # 3. State Reconciler Tests (Conservative Safeguards)
    print("3. Probando Reconciliador de Estado Conservador...")
    
    # Test 3A: Clean State Sync
    mock_adapter = MagicMock()
    mock_adapter.fetch_open_orders = AsyncMock(return_value=[])
    mock_adapter.fetch_positions = AsyncMock(return_value=[])
    
    reconciler = StateReconciler(exchange_adapter=mock_adapter)
    clean_result = await reconciler.reconcile(local_open_orders=[], local_open_positions=[])
    assert clean_result.is_clean is True
    assert clean_result.requires_manual_intervention is False
    assert reconciler.is_locked_for_review is False
    print("   [OK] Reconciliacion Limpia: Bot habilitado para operar.")

    # Test 3B: Discrepancy - Orphan Order on Exchange
    mock_adapter.fetch_open_orders = AsyncMock(return_value=[
        {"id": "EX_9999", "symbol": "BTC/USDT", "amount": 0.5, "price": 60000}
    ])
    discrepancy_result = await reconciler.reconcile(local_open_orders=[], local_open_positions=[])
    assert discrepancy_result.is_clean is False
    assert discrepancy_result.requires_manual_intervention is True
    assert reconciler.is_locked_for_review is True
    assert len(discrepancy_result.discrepancies) == 1
    assert discrepancy_result.discrepancies[0].discrepancy_type == "ORPHAN_EXCHANGE_ORDER"
    print("   [OK] Salvaguarda de Discrepancia: Orden huerfana detectada -> Bot BLOQUEADO para revision manual.")

    # Test 3C: Discrepancy - Unknown Position on Exchange
    mock_adapter.fetch_open_orders = AsyncMock(return_value=[])
    mock_adapter.fetch_positions = AsyncMock(return_value=[
        {"symbol": "ETH/USDT", "contracts": 2.5}
    ])
    pos_discrepancy = await reconciler.reconcile(local_open_orders=[], local_open_positions=[])
    assert pos_discrepancy.is_clean is False
    assert pos_discrepancy.requires_manual_intervention is True
    assert reconciler.is_locked_for_review is True
    assert pos_discrepancy.discrepancies[0].discrepancy_type == "POSITION_MISMATCH"
    print("   [OK] Salvaguarda de Posicion: Posicion no registrada detectada -> Bot BLOQUEADO para revision manual.")

    print("==================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE FASE 2 PASARON CON EXITO")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase2_tests())
