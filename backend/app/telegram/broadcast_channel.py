"""Broadcast Service for Telegram Messages with 100% Intuitive Spanish Formats."""
from decimal import Decimal
from typing import Optional
from app.core.constants import SignalType
from app.strategies.base_strategy import StrategySignal


class TelegramBroadcastService:
    """Formats ultra-clear, intuitive messages for Telegram."""

    @staticmethod
    def format_signal_broadcast(
        signal: StrategySignal,
        invested_amount: Optional[Decimal] = None,
        available_cash: Optional[Decimal] = None,
        mode_label: str = "DEMO (Binance en Vivo)",
        duration_minutes: int = 1,
        active_concurrent: Optional[str] = None,
    ) -> str:
        """Formats a clear notification when a buy order is placed."""
        direction = "PUT" if (getattr(signal, "metadata", {}) and signal.metadata.get("direction") == "PUT") or signal.signal_type == SignalType.SELL else "CALL"
        is_put = direction == "PUT"

        price_str = f"${signal.price:,.2f}" if signal.price >= 10 else f"{signal.price:.5f}"
        dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"
        invested_str = f"${invested_amount:,.2f} USD" if invested_amount else "Asignada automáticamente"

        clean_symbol = signal.symbol.replace("-OTC", "")
        concurrent_line = f"\n📊 <b>Operaciones simultáneas:</b> <code>{active_concurrent}</code>" if active_concurrent else ""
        if is_put:
            return (
                f"🔴 <b>NUEVA OPERACIÓN: PUT (BAJADA)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"💵 <b>Inversión:</b> <code>{invested_str}</code>\n"
                f"⏱️ <b>Tiempo:</b> <code>{dur_str}</code>\n"
                f"🎯 <b>Señal:</b> <i>Agotamiento en resistencia</i>{concurrent_line}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            return (
                f"🟢 <b>NUEVA OPERACIÓN: CALL (SUBIDA)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"💵 <b>Inversión:</b> <code>{invested_str}</code>\n"
                f"⏱️ <b>Tiempo:</b> <code>{dur_str}</code>\n"
                f"🎯 <b>Señal:</b> <i>Rebote institucional en soporte</i>{concurrent_line}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

    @staticmethod
    def format_trade_closed_broadcast(
        symbol: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        net_pnl: Decimal,
        pnl_pct: Decimal,
        exit_reason: str,
        account_equity: Optional[Decimal] = None,
        mode_label: str = "DEMO (IQ Option)",
    ) -> str:
        """Formats trade closure results in clean, VIP style."""
        is_win = net_pnl >= Decimal("0")
        clean_symbol = symbol.replace("-OTC", "")
        equity_str = f"${account_equity:,.2f} USD" if account_equity is not None else "Actualizado"

        if is_win:
            return (
                f"🏆 <b>¡OPERACIÓN GANADA! (+{pnl_pct:,.1f}%)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"💰 <b>Ganancia Neta:</b> <b>+{net_pnl:,.2f} USD</b>\n"
                f"📈 <b>Saldo en Cuenta:</b> <b>{equity_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            return (
                f"🛡️ <b>OPERACIÓN CERRADA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"📉 <b>Resultado:</b> <b>-${abs(net_pnl):,.2f} USD</b>\n"
                f"📈 <b>Saldo en Cuenta:</b> <b>{equity_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

    async def broadcast_to_channel(self, text: str) -> bool:
        """Sends an intuitive broadcast message directly to Telegram channel or admin chat."""
        from app.telegram.telegram_client import get_telegram_client
        from app.core.config import settings
        from app.core.logger import logger

        client = get_telegram_client()
        target_chat = settings.TELEGRAM_CHANNEL_ID or settings.TELEGRAM_ADMIN_CHAT_ID
        if not client or not target_chat:
            logger.warning("[BROADCAST] Cannot send message: Telegram client or chat ID not set.")
            return False
        try:
            await client.send_message(target_chat, text)
            logger.info(f"[BROADCAST] Message delivered to Telegram chat {target_chat}")
            return True
        except Exception as e:
            logger.error(f"[BROADCAST] Failed to send message to Telegram: {e}")
            return False
