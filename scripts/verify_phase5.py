"""Phase 5 Verification Script: Telegram Interactive Hub, Admin & Broadcast."""
import asyncio
import sys
import os
import time
from decimal import Decimal
from unittest.mock import MagicMock

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.constants import BotMode, CircuitBreakerStatus, SignalType
from app.strategies.base_strategy import StrategySignal
from app.engine.risk_manager import RiskManager
from app.engine.state_reconciler import StateReconciler
from app.telegram.interactive_signal import InteractiveSignalManager
from app.telegram.admin_handlers import TelegramAdminHandler
from app.telegram.heartbeat import HeartbeatWatchdog
from app.telegram.broadcast_channel import TelegramBroadcastService


async def run_phase5_tests():
    print("==================================================")
    print("[START] INICIANDO VERIFICACION DE FASE 5 (TDD)")
    print("==================================================")

    # 1. Interactive Signal Manager Tests (TTL & Price Drift)
    print("1. Probando Gestor de Senales Interactivas (TTL 45s & Price Drift)...")
    sig_mgr = InteractiveSignalManager(default_ttl_seconds=1)  # 1s for quick test
    sample_signal = StrategySignal(
        symbol="BTC/USDT",
        signal_type=SignalType.BUY,
        price=Decimal("60000.00"),
        stop_loss=Decimal("59000.00"),
        take_profit=Decimal("62000.00"),
        pattern_name="DOUBLE_BOTTOM",
        reason="Doble suelo confirmado con volumen."
    )
    
    pending = sig_mgr.create_pending_signal(sample_signal, signal_id="SIG_001")
    assert pending.signal_id == "SIG_001"
    assert pending.is_resolved is False

    # Test 1A: Price Drift Expiration (>0.3% move)
    is_expired, reason = sig_mgr.check_expiration("SIG_001", current_market_price=Decimal("60300.00")) # 0.5% move
    assert is_expired is True
    assert "Price drifted" in reason
    print("   [OK] Expiracion por Desplazamiento de Precio: Senal cancelada preventivamente.")

    # Test 1B: TTL Timeout Expiration
    pending_timeout = sig_mgr.create_pending_signal(sample_signal, signal_id="SIG_002")
    await asyncio.sleep(1.1)
    is_timeout_expired, timeout_reason = sig_mgr.check_expiration("SIG_002")
    assert is_timeout_expired is True
    assert "Timeout" in timeout_reason
    print("   [OK] Expiracion por Tiempo (TTL): Senal auto-cancelada a los 45s.")

    # Test 1C: Interactive Approval
    sig_mgr_live = InteractiveSignalManager(default_ttl_seconds=45)
    pending_live = sig_mgr_live.create_pending_signal(sample_signal, signal_id="SIG_003")
    success, approved_sig, msg = sig_mgr_live.resolve_signal("SIG_003", approve=True, operator_id="admin_123")
    assert success is True
    assert approved_sig is not None
    assert approved_sig.symbol == "BTC/USDT"
    print("   [OK] Aprobacion Interactiva: Boton [Aprobar] ejecutado por el administrador.")

    # 2. Admin Handlers Tests (/panic & /resume_after_review)
    print("2. Probando Comandos Administrativos (/panic y /resume_after_review)...")
    mock_adapter = MagicMock()
    reconciler = StateReconciler(mock_adapter)
    rm = RiskManager()
    admin_handler = TelegramAdminHandler(rm, reconciler, sig_mgr_live)

    # Execute /panic
    panic_response = admin_handler.handle_panic_command(user_id="owner_user")
    assert rm.circuit_breaker.status == CircuitBreakerStatus.TRIPPED
    assert admin_handler.is_panic_stopped is True
    assert "PARADA DE EMERGENCIA" in panic_response
    print("   [OK] Comando /panic: Circuit breaker disparado y bot bloqueado de inmediato.")

    # Execute /resume_after_review without justification -> Must fail
    bad_resume = admin_handler.handle_resume_after_review(user_id="owner_user", reason="")
    assert "Error de formato" in bad_resume

    # Execute /resume_after_review with valid justification -> Must succeed
    good_resume = admin_handler.handle_resume_after_review(
        user_id="owner_user",
        reason="Posicion revisada en Binance, orden manual cancelada, seguro reanudar"
    )
    assert rm.circuit_breaker.status == CircuitBreakerStatus.NORMAL
    assert admin_handler.is_panic_stopped is False
    assert reconciler.is_locked_for_review is False
    assert "SISTEMA REANUDADO" in good_resume
    print("   [OK] Comando /resume_after_review: Reanudacion intencional y documentada verificada.")

    # 3. Heartbeat Watchdog Tests
    print("3. Probando Heartbeat Watchdog de Monitoreo...")
    watchdog = HeartbeatWatchdog()
    hb_msg = watchdog.format_heartbeat_message(
        mode=BotMode.PAPER,
        circuit_status=CircuitBreakerStatus.NORMAL,
        equity=Decimal("10000.00"),
        active_positions_count=1,
        is_reconciled=True
    )
    assert "BOT HEARTBEAT" in hb_msg
    assert "Uptime" in hb_msg
    assert "$10,000.00" in hb_msg
    print("   [OK] Heartbeat Watchdog: Formateo de pulso vital del bot completado.")

    # 4. Broadcast Channel Service Tests
    print("4. Probando Publicacion en Canal/Grupo...")
    broadcast_msg = TelegramBroadcastService.format_signal_broadcast(sample_signal)
    assert "NUEVA SEÑAL DETECTADA" in broadcast_msg
    assert "DOUBLE_BOTTOM" in broadcast_msg

    closed_msg = TelegramBroadcastService.format_trade_closed_broadcast(
        symbol="BTC/USDT",
        side="buy",
        entry_price=Decimal("60000.00"),
        exit_price=Decimal("62000.00"),
        net_pnl=Decimal("195.50"),
        pnl_pct=Decimal("3.25"),
        exit_reason="TAKE_PROFIT"
    )
    assert "OPERACIÓN CERRADA" in closed_msg
    assert "+$195.50" in closed_msg
    print("   [OK] Broadcast Service: Retransmision atractiva para canales verificada.")

    print("==================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE FASE 5 PASARON CON EXITO")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase5_tests())
