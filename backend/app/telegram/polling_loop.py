"""Telegram Long-Polling Loop.

Runs as a background asyncio task launched from main.py lifespan.
Dispatches incoming commands and inline button callbacks to the appropriate handlers.
"""
import asyncio
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logger import logger
from app.telegram.telegram_client import TelegramClient


class TelegramPollingLoop:
    """
    Long-polling consumer for Telegram updates.
    Routes commands (/panic, /status, /resume_after_review) and inline callbacks.
    """

    def __init__(self, client: TelegramClient):
        self._client = client
        self._offset: int = 0
        self._running: bool = False

    async def start(self) -> None:
        """Starts the long-polling loop. Designed to run as a background task."""
        self._running = True
        logger.info("[TELEGRAM POLLING] Long-polling loop started.")

        while self._running:
            try:
                updates = await self._client.get_updates(
                    offset=self._offset,
                    timeout=30,
                    allowed_updates=["message", "callback_query"],
                )
                for update in updates:
                    self._offset = update["update_id"] + 1
                    await self._dispatch(update)
            except asyncio.CancelledError:
                logger.info("[TELEGRAM POLLING] Loop cancelled — shutting down.")
                break
            except Exception as e:
                logger.error(f"[TELEGRAM POLLING] Unexpected error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back-off before retry on unexpected errors

    def stop(self) -> None:
        self._running = False

    async def _dispatch(self, update: Dict[str, Any]) -> None:
        """Routes an update to the correct handler."""
        # Import here to avoid circular imports at module load time
        from app.engine.bot_runner import bot_runner

        # ── Inline button callbacks ────────────────────────────────────────
        callback_query = update.get("callback_query")
        if callback_query:
            await self._handle_callback(callback_query)
            return

        # ── Text commands ──────────────────────────────────────────────────
        message = update.get("message", {})
        text: str = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))
        user_id = str(message.get("from", {}).get("id", ""))
        username = message.get("from", {}).get("username", user_id)

        if not text or not chat_id:
            return

        # Security: only respond to the configured admin chat
        if chat_id != settings.TELEGRAM_ADMIN_CHAT_ID:
            logger.warning(f"[TELEGRAM POLLING] Message from unauthorized chat {chat_id} ignored.")
            return

        logger.info(f"[TELEGRAM POLLING] Command from @{username}: {text}")
        keyboard = bot_runner.admin_handler.get_main_menu_keyboard()

        # Iniciar Bot / Trading
        if (
            text.startswith("/iniciar")
            or text.startswith("/start_bot")
            or text == "▶️ Iniciar Trading"
            or text == "▶️ Iniciar Bot"
            or text == "/start"
        ):
            import time
            await bot_runner._refresh_balance()
            if hasattr(bot_runner, "session_manager"):
                bot_runner.session_manager.reset_session(current_equity=bot_runner.equity)
                bot_runner.session_manager.cycle_state = "ACTIVE"
                bot_runner.session_manager.cycle_start_time = time.time()
            bot_runner.is_running = True
            t_pct = bot_runner.session_manager.target_mode if hasattr(bot_runner, "session_manager") else "3.5%"
            response = bot_runner.admin_handler.handle_start_bot(username, target_pct=t_pct)
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Pausar / Detener Trading
        elif (
            text.startswith("/parar")
            or text.startswith("/stop")
            or text.startswith("/pausar")
            or text == "⏹️ Parar Trading"
            or text == "⏹️ Pausar Bot"
        ):
            bot_runner.is_running = False
            response = bot_runner.admin_handler.handle_pause_bot(username)
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Meta de Ganancia y Progreso
        elif text.startswith("/meta") or text.startswith("/target") or "Meta" in text:
            if hasattr(bot_runner, "session_manager"):
                progress_data = bot_runner.session_manager.get_progress_data()
                response = bot_runner.admin_handler.handle_target_progress_report(progress_data)
            else:
                response = "🎯 <b>Módulo de Metas no inicializado todavía.</b>"
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Modo Horas (Ciclo 1h operando / 1h descanso)
        elif text.startswith("/horas") or text.startswith("/ciclo") or text == "⏱️ Modo Horas":
            if hasattr(bot_runner, "session_manager"):
                response = bot_runner.admin_handler.handle_toggle_hourly_cycle(bot_runner.session_manager)
            else:
                response = "⏱️ <b>Gestor de sesiones no activo.</b>"
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Configurar Meta (3%, 4%, 5%, AUTO)
        elif text.startswith("/set_meta") or text in ("/meta_3", "/meta_4", "/meta_5", "/meta_auto") or text == "⚙️ Fijar Meta":
            if hasattr(bot_runner, "session_manager"):
                if text == "⚙️ Fijar Meta":
                    response = (
                        "⚙️ <b>CONFIGURAR META DE GANANCIA</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "Selecciona la meta diaria para tu sesión enviando el comando:\n\n"
                        "• <code>/meta_3</code> ➔ Meta del <b>+3.0%</b> (Conservador / Seguro) 🛡️\n"
                        "• <code>/meta_4</code> ➔ Meta del <b>+4.0%</b> (Equilibrado) ⚖️\n"
                        "• <code>/meta_5</code> ➔ Meta del <b>+5.0%</b> (Objetivo Máximo) 🚀\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "<i>El bot calculará los dólares y se auto-apagará al llegar al objetivo.</i>"
                    )
                else:
                    parts = text.split(maxsplit=1)
                    mode_arg = parts[1] if len(parts) > 1 else text.replace("/meta_", "")
                    response = bot_runner.admin_handler.handle_set_target(bot_runner.session_manager, mode_arg)
            else:
                response = "⚙️ <b>Gestor de sesiones no activo.</b>"
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Estado y Balance
        elif text.startswith("/status") or text.startswith("/balance") or "Saldo" in text or text == "📊 Estado y Balance":
            await bot_runner._refresh_balance()
            thoughts = bot_runner.strategy.get_latest_thoughts() if hasattr(bot_runner.strategy, "get_latest_thoughts") else {}
            t_mode = bot_runner.session_manager.target_mode if hasattr(bot_runner, "session_manager") else "3.5%"
            response = bot_runner.admin_handler.handle_status_command(
                current_equity=bot_runner.equity,
                mode=bot_runner.mode,
                is_running=bot_runner.is_running,
                ai_thoughts=thoughts,
                target_mode=t_mode,
            )
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Radar en Vivo de la IA
        elif text.startswith("/radar") or text == "🎯 Radar IA":
            thoughts = bot_runner.strategy.get_latest_thoughts() if hasattr(bot_runner.strategy, "get_latest_thoughts") else {}
            lines = []
            if thoughts:
                for s, t in thoughts.items():
                    clean_s = s.replace("-OTC", "")
                    lines.append(f"🪙 <b>{clean_s}:</b> <i>{t}</i>")
                msg_body = "\n\n".join(lines)
            else:
                msg_body = "• <i>Analizando mercado... Las confluencias se calcularán en el próximo bloque de velas de 1m.</i>"
            resp = (
                "🎯 <b>RADAR DE ESCANEO DE LA IA EN VIVO</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{msg_body}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>El bot solo ejecutará una orden cuando coincidan: Bollinger Extremo + RSI Extremo + Vela de Rechazo.</i>"
            )
            await self._client.send_message(chat_id, resp, reply_markup=keyboard)

        # Ganancias y Rendimiento
        elif text.startswith("/ganancias") or text.startswith("/pnl") or text == "💰 Ganancias / PnL":
            response = bot_runner.admin_handler.handle_pnl_report(
                equity=bot_runner.equity,
                initial_equity=getattr(bot_runner, "initial_equity", bot_runner.equity),
            )
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Sentimiento e Inteligencia Web
        elif text.startswith("/sentimiento") or text == "🌐 Sentimiento Mercado":
            from app.services.sentiment_service import sentiment_service
            sentiment_data = await sentiment_service.get_sentiment()
            response = bot_runner.admin_handler.handle_sentiment_report(sentiment_data)
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Aprendizaje de la IA
        elif text.startswith("/ia") or text.startswith("/learn") or text == "🧠 Aprendizaje IA":
            ai_stats = bot_runner.strategy.get_stats() if hasattr(bot_runner.strategy, "get_stats") else {}
            response = bot_runner.admin_handler.handle_ai_stats_report(ai_stats)
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        # Parada de Emergencia
        elif text.startswith("/panic"):
            response = bot_runner.admin_handler.handle_panic_command(username)
            bot_runner.is_running = False
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        elif text.startswith("/resume_after_review"):
            parts = text.split(maxsplit=1)
            reason = parts[1].strip() if len(parts) > 1 else ""
            response = bot_runner.admin_handler.handle_resume_after_review(
                user_id=username,
                reason=reason,
            )
            if reason and len(reason.strip()) >= 4:
                bot_runner.is_running = True
            await self._client.send_message(chat_id, response, reply_markup=keyboard)

        elif text.startswith("/help") or text.startswith("/ayuda") or text == "ℹ️ Ayuda":
            await self._client.send_message(chat_id, _help_message(), reply_markup=keyboard)

        else:
            await self._client.send_message(
                chat_id,
                f"❓ <b>Opción:</b> <code>{text}</code>\nUsa los botones táctiles aquí abajo 👇",
                reply_markup=keyboard
            )

    async def _handle_callback(self, callback_query: Dict[str, Any]) -> None:
        """Handles inline keyboard button presses (signal approve/reject)."""
        from app.engine.bot_runner import bot_runner

        callback_id = callback_query.get("id", "")
        data: str = callback_query.get("data", "")
        user = callback_query.get("from", {})
        user_id = str(user.get("id", ""))
        username = user.get("username", user_id)
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))

        # Acknowledge immediately to remove the spinner
        await self._client.answer_callback_query(callback_id)

        # Expected data format: "signal:APPROVE:signal_uuid" or "signal:REJECT:signal_uuid"
        parts = data.split(":")
        if len(parts) == 3 and parts[0] == "signal":
            action = parts[1]   # APPROVE | REJECT
            signal_id = parts[2]
            response = bot_runner.admin_handler.handle_signal_callback(
                signal_id=signal_id,
                action=action,
                user_id=username,
            )
            await self._client.send_message(chat_id, response)
        else:
            logger.warning(f"[TELEGRAM POLLING] Unknown callback data: {data}")


def _help_message() -> str:
    return (
        "🤖 <b>CENTRO DE CONTROL DEL TRADING BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Puedes usar los botones táctiles o los siguientes comandos:\n\n"
        "▶️ <b>/iniciar</b> — Arranca el bot y el análisis continuo\n"
        "⏹️ <b>/parar</b> — Pausa las nuevas compras con seguridad\n"
        "📊 <b>/balance</b> — Consulta tu capital y posiciones abiertas\n"
        "💰 <b>/ganancias</b> — Extracto de PnL y resultados acumulados\n"
        "🌐 <b>/sentimiento</b> — Consulta en internet el Fear & Greed Index\n"
        "🚨 <b>/panic</b> — Parada forzada de emergencia y cierre inmediato\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Toca los botones del menú en tu teclado para controlar todo con un toque.</i>"
    )
