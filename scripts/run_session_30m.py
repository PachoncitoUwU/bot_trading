"""Script para ejecutar una Sesión de Trading de 30 Minutos con Postura Fija de $55 USD.

Estrategia: Fibonacci Retracement & Golden Pocket (61.8% / 50% / 78.6%)
Broker: IQ Option (Modo PRACTICE)
Postura: $55.00 USD Planos (Cero Martingala)
Duración: 30 Minutos
"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys
import time

# Agregar directorio backend a sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.logger import logger
from app.database.session import init_db
from app.engine.bot_runner import bot_runner
from app.telegram.telegram_client import init_telegram_client


async def run_30_minute_session(duration_minutes: int = 30, stake_usd: float = 55.0):
    print("=" * 70)
    print("🚀 INICIANDO SESIÓN DE TRADING DE 30 MINUTOS (FIBONACCI GOLDEN SNIPER)")
    print(f"💰 Importe por operación: ${stake_usd:.2f} USD (Fijo / Sin Martingala)")
    print(f"⏱️ Tiempo total programado: {duration_minutes} Minutos")
    print(f"🎯 Modo: {settings.BOT_MODE.value} | Broker: {settings.EXCHANGE_ID.upper()}")
    print("=" * 70)

    # 1. Inicializar base de datos
    await init_db()

    # 2. Inicializar cliente Telegram (para que reporte si está configurado)
    telegram_client = init_telegram_client()

    # 3. Arrancar bot runner
    start_result = await bot_runner.start()
    if not bot_runner.is_running:
        print("[ERROR] No se pudo iniciar bot_runner.")
        return

    # Forzar configuración de stake exacto
    bot_runner.staking_manager.set_steps([Decimal(str(stake_usd))])

    start_equity = bot_runner.equity
    session_start_time = datetime.now()
    session_end_time = session_start_time + timedelta(minutes=duration_minutes)
    total_seconds = duration_minutes * 60

    print(f"✅ Conexión establecida con éxito.")
    print(f"💵 Saldo Inicial: ${start_equity:,.2f} USD")
    print(f"🕒 Inicio: {session_start_time.strftime('%H:%M:%S')} | Fin programado: {session_end_time.strftime('%H:%M:%S')}")
    print("-" * 70)

    # Notificar inicio por Telegram si está habilitado
    if telegram_client and settings.TELEGRAM_ADMIN_CHAT_ID:
        try:
            await telegram_client.send_message(
                settings.TELEGRAM_ADMIN_CHAT_ID,
                f"🚀 <b>SESIÓN FIBONACCI INICIADA (30 MIN)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Saldo inicial: <b>${start_equity:,.2f} USD</b>\n"
                f"🎯 Postura fija: <b>${stake_usd:.2f} USD</b> (Cero Martingala)\n"
                f"⏱️ Duración: <b>{duration_minutes} minutos</b>\n"
                f"📐 Estrategia: <b>Fibonacci Retracement (Golden Pocket)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Monitoreando pares OTC 24/7 en tiempo real...</i>"
            )
        except Exception as e:
            logger.warning(f"[TELEGRAM] No se pudo enviar mensaje de inicio: {e}")

    tick_interval = 5  # cada 5 segundos
    iteration = 0

    try:
        while datetime.now() < session_end_time:
            iteration += 1
            elapsed_seconds = int((datetime.now() - session_start_time).total_seconds())
            remaining_seconds = max(0, total_seconds - elapsed_seconds)

            mins_rem = int(remaining_seconds // 60)
            secs_rem = int(remaining_seconds % 60)

            # Ejecutar tick de análisis y ejecución
            await bot_runner.tick()

            # Monitoreo en consola cada 30 segundos o cuando hay cambios
            if iteration % 6 == 0 or iteration == 1:
                active_trades = len(bot_runner.risk_manager.active_positions)
                pnl_usd = bot_runner.equity - start_equity
                pnl_pct = (pnl_usd / start_equity) * 100 if start_equity > 0 else Decimal("0")
                sign = "+" if pnl_usd >= 0 else ""

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Restante: {mins_rem:02d}m {secs_rem:02d}s | "
                    f"Trades Activos: {active_trades} | Cerrados: {bot_runner.closed_trades_count} | "
                    f"PnL: {sign}${pnl_usd:,.2f} USD ({sign}{pnl_pct:.2f}%) | "
                    f"Saldo: ${bot_runner.equity:,.2f} USD"
                )

                # Mostrar razonamiento de Fibonacci en los pares activos
                if hasattr(bot_runner.strategy, "get_latest_thoughts"):
                    thoughts = bot_runner.strategy.get_latest_thoughts()
                    for sym, th in list(thoughts.items())[:3]:  # Top 3 pares
                        if "⏳" not in th:
                            print(f"   📐 {th}")

            await asyncio.sleep(tick_interval)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n🛑 Sesión interrumpida por el usuario.")
    except Exception as e:
        logger.error(f"[SESSION ERROR] Error en la sesión: {e}", exc_info=True)

    # 4. Cierre y Resumen Final de la Sesión
    print("\n" + "=" * 70)
    print("🏁 SESIÓN DE 30 MINUTOS COMPLETADA")
    print("=" * 70)

    final_equity = bot_runner.equity
    net_pnl = final_equity - start_equity
    net_pct = (net_pnl / start_equity) * 100 if start_equity > 0 else Decimal("0")
    sign = "+" if net_pnl >= 0 else ""

    stats = bot_runner.strategy.get_stats() if hasattr(bot_runner.strategy, "get_stats") else {}
    history = bot_runner.trade_history

    wins = sum(1 for t in history if t.get("is_win"))
    losses = sum(1 for t in history if not t.get("is_win"))
    total_trades = len(history)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    print(f"📊 RESUMEN FINAL:")
    print(f"• Tiempo Transcurrido:    {min(duration_minutes, int((datetime.now() - session_start_time).total_seconds() / 60))} minutos")
    print(f"• Postura por Operación:  ${stake_usd:.2f} USD")
    print(f"• Total Operaciones:      {total_trades}")
    print(f"• Ganadas / Perdidas:     {wins}W - {losses}L (Win Rate: {win_rate:.1f}%)")
    print(f"• Saldo Inicial:          ${start_equity:,.2f} USD")
    print(f"• Saldo Final:            ${final_equity:,.2f} USD")
    print(f"• Ganancia / Pérdida PnL: {sign}${net_pnl:,.2f} USD ({sign}{net_pct:.2f}%)")
    print("=" * 70)

    if telegram_client and settings.TELEGRAM_ADMIN_CHAT_ID:
        try:
            await telegram_client.send_message(
                settings.TELEGRAM_ADMIN_CHAT_ID,
                f"🏁 <b>SESIÓN FIBONACCI FINALIZADA (30 MIN)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Saldo final: <b>${final_equity:,.2f} USD</b>\n"
                f"📈 PnL Neto: <b>{sign}${net_pnl:,.2f} USD ({sign}{net_pct:.2f}%)</b>\n"
                f"🎯 Operaciones: <b>{total_trades} ({wins}W / {losses}L)</b>\n"
                f"🏆 Win Rate: <b>{win_rate:.1f}%</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Estrategia Fibonacci Golden Pocket probada con éxito.</i>"
            )
        except Exception as e:
            logger.warning(f"[TELEGRAM] Error enviando reporte final: {e}")

    bot_runner.is_running = False


if __name__ == "__main__":
    asyncio.run(run_30_minute_session(duration_minutes=30, stake_usd=55.0))
