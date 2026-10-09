"""
Weekend Autopilot Trading Launcher (IQ Option Fibonacci Quantitative Engine).
Runs autonomously in 7-trade sections followed by 50-minute market rest cooldowns,
operating from Friday afternoon through Sunday midnight (2026-10-11 23:59:59).
Zero manual intervention required.
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.logger import logger
from app.core.power_manager import enable_24_7_execution_mode
from app.database.session import init_db
from app.engine.bot_runner import bot_runner
from app.telegram.telegram_client import init_telegram_client, get_telegram_client


async def main():
    logger.info("================================================================================")
    logger.info("  🚀 AUTOPILOT FIN DE SEMANA INICIADO (VIERNES A DOMINGO 23:59:59) 🚀")
    logger.info("================================================================================")
    logger.info("  • Estrategia: Fibonacci Retracement (Golden Pocket 61.8% / 50% / 78.6%)")
    logger.info("  • Modalidad: Tandas de 7 operaciones con descansos de 50 minutos entre secciones")
    logger.info("  • Inversión: $55.00 USD fija por operación (Cero Martingala)")
    logger.info("  • Mercados: 11 Pares OTC con filtro de mecha de rechazo")
    logger.info("  • Cierre: Domingo 11 de Octubre a las 23:59:59 automático")
    logger.info("================================================================================")

    # 1. Enable Windows anti-sleep mode
    enable_24_7_execution_mode()

    # 2. Initialize database
    await init_db()

    # 3. Initialize Telegram client
    init_telegram_client()

    # 4. Start bot runner
    await bot_runner.start()
    bot_runner.is_running = True

    # 5. Announce start on Telegram
    tg_client = get_telegram_client()
    target_chat = settings.TELEGRAM_ADMIN_CHAT_ID or settings.TELEGRAM_CHANNEL_ID
    if tg_client and target_chat:
        start_announcement = (
            "🤖 <b>AUTOPILOT FIN DE SEMANA ACTIVADO</b> 🤖\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📅 <b>Duración:</b> Viernes hasta Domingo 23:59:59 (100% Autónomo)\n"
            "🧠 <b>Estrategia:</b> Fibonacci Golden Pocket (0.618 / 0.50 / 0.786)\n"
            "💵 <b>Inversión:</b> $55.00 USD por operación (Fija / Sin doblar)\n"
            "🔄 <b>Modalidad por Tandas:</b>\n"
            "• Opera hasta <b>7 operaciones</b> por sección.\n"
            "• Al terminar cada tanda, toma un <b>reposo de 50 minutos</b> para enfriar el mercado.\n"
            "• Reanuda la siguiente tanda sola sin intervención manual.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Saldo Inicial:</b> <b>${bot_runner.equity:,.2f} USD</b>\n"
            "🔍 <b>Mercados:</b> 11 Pares OTC de alta volatilidad\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No tienes que tocar nada en Telegram ni en tu PC. El sistema operará y reportará cada resultado automáticamente.</i>"
        )
        try:
            keyboard = bot_runner.admin_handler.get_main_menu_keyboard()
            await tg_client.send_message(target_chat, start_announcement, reply_markup=keyboard)
        except Exception as e:
            logger.debug(f"[AUTOPILOT] Error sending startup message: {e}")

    # 6. Main execution loop
    tick_count = 0
    try:
        while bot_runner.is_running or (bot_runner.session_manager.weekend_autopilot and not bot_runner.session_manager.is_weekend_finished()):
            try:
                if bot_runner.is_running:
                    await bot_runner.tick()
                else:
                    # If paused but weekend autopilot is active and resting
                    can_trade, reason, just_resumed = bot_runner.session_manager.check_cycle_status()
                    if just_resumed:
                        bot_runner.is_running = True
                        await bot_runner._send_section_resumed_notification()
            except Exception as tick_err:
                logger.error(f"[AUTOPILOT] Error en tick: {tick_err}", exc_info=True)

            await asyncio.sleep(5)
            tick_count += 1
            if tick_count % 60 == 0:
                prog = bot_runner.session_manager.get_progress_data()
                logger.info(
                    f"[AUTOPILOT HEARTBEAT] Estado: {prog.get('cycle_state')} | Saldo: ${bot_runner.equity:,.2f} | "
                    f"Ops fin de semana: {prog.get('total_weekend_trades', 0)} ({prog.get('total_weekend_wins', 0)}W - {prog.get('total_weekend_losses', 0)}L) | "
                    f"PnL: ${prog.get('total_weekend_profit', 0):,.2f}"
                )
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[AUTOPILOT] Parada manual solicitada.")
    finally:
        logger.info("[AUTOPILOT] Ciclo finalizado.")


if __name__ == "__main__":
    asyncio.run(main())
