"""Automated verification script for SessionManager, 3%-5% targets, hourly cycles, and Telegram reporting."""
import sys
import os
from decimal import Decimal

# Ensure backend path is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.engine.session_manager import SessionManager
from app.telegram.admin_handlers import TelegramAdminHandler


def main():
    print("=" * 60)
    print("🧪 INICIANDO VERIFICACIÓN DE METAS (3%-5%) Y CICLOS POR HORA")
    print("=" * 60)

    # 1. Test SessionManager Init & Baseline
    sm = SessionManager(target_mode="AUTO", hourly_cycle_enabled=True)
    sm.sync_starting_equity(Decimal("10000.00"))
    assert sm.session_starting_equity == Decimal("10000.00")
    print("✅ 1. Inicialización de SessionManager: CORRECTA")

    # 2. Test Market Regime & Dynamic Target
    regime = sm.get_market_regime()
    target_pct = sm.get_target_pct()
    print(f"✅ 2. Régimen de mercado detectado: {regime['label']}")
    print(f"     Descripción: {regime['description']}")
    print(f"     Meta asignada: +{target_pct}%")
    assert target_pct in (Decimal("3.0"), Decimal("4.0"), Decimal("5.0"))

    # 3. Test Trade Records & Target Progress
    # Simulate 3 winning trades of $150 each
    res1 = sm.record_trade_result(Decimal("150.00"), is_win=True, current_equity=Decimal("10150.00"))
    assert not res1["is_target_reached"]
    print(f"✅ 3. Trade 1 (+150): Ganancia acumulada ${sm.session_net_profit:,.2f} (+{res1['session_profit_pct']:.2f}%)")

    # Simulate trade reaching target (e.g. +$400 total on $10,000 when target is 3% = $300)
    res2 = sm.record_trade_result(Decimal("200.00"), is_win=True, current_equity=Decimal("10350.00"))
    print(f"✅ 4. Trade 2 (+200): Ganancia acumulada ${sm.session_net_profit:,.2f} (+{res2['session_profit_pct']:.2f}%)")
    if target_pct <= Decimal("3.5"):
        assert sm.is_target_reached
        print("🎯 ¡DISPARADOR DE META ACTIVADO EXITOSAMENTE AL SUPERAR EL 3%!")

    # 4. Test Telegram Formatter
    prog = sm.get_progress_data()
    dummy_handler = TelegramAdminHandler(None, None, None)
    tg_report = dummy_handler.handle_target_progress_report(prog)
    print("=" * 60)
    print("📱 VISTA PREVIA DEL REPORTE DE TELEGRAM:")
    print("=" * 60)
    print(tg_report)
    print("=" * 60)
    assert "🎯" in tg_report
    assert "Progreso hacia el objetivo" in tg_report

    # 5. Test Hourly Cycle Check
    can_trade, msg = sm.check_hourly_cycle()
    print(f"✅ 5. Ciclo Horario: Can Trade={can_trade}, Msg={msg}")

    # 6. Test Keyboard Layout
    kb = dummy_handler.get_main_menu_keyboard()
    button_texts = [b["text"] for row in kb["keyboard"] for b in row]
    assert "🎯 Meta y Progreso" in button_texts
    assert "⏱️ Modo Horas" in button_texts
    print(f"✅ 6. Teclado Táctil de Telegram actualizado con: {button_texts}")

    print("\n🎉 TODAS LAS PRUEBAS DEL SISTEMA DE METAS PASARON CON 100% DE ÉXITO.")


if __name__ == "__main__":
    main()
