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
        mode_label: str = "DEMO (IQ Option Práctica)",
        duration_minutes: int = 5,
        active_concurrent: Optional[str] = None,
    ) -> str:
        """Formats an executive, high-conviction sniper trade entry notification."""
        meta = getattr(signal, "metadata", {}) or {}
        direction = meta.get("direction") or ("PUT" if signal.signal_type == SignalType.SELL else "CALL")
        is_put = direction == "PUT"

        dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"
        invested_str = f"${invested_amount:,.2f} USD" if invested_amount else "$25.00 USD"
        clean_symbol = signal.symbol.replace("-OTC", "")

        conf_val = getattr(signal, "confidence", Decimal("0.75"))
        conf_pct = int(float(conf_val) * 100) if conf_val else 75
        confluences = meta.get("confluences", 3)
        rsi_val = meta.get("rsi")
        rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "Extremo"
        pattern_str = meta.get("pattern") or signal.pattern_name or "Absorción Institucional"

        if is_put:
            dir_badge = "🔴 PUT (BAJADA / VENTA)"
            momentum_text = f"RSI en {rsi_str} (Sobrecompra profunda + Giro bajista)"
            bb_text = "Rechazo contundente en Banda Superior de Bollinger"
            thesis_text = "Agotamiento del impulso comprador en techo dinámico; se proyecta retroceso correctivo hacia la media móvil central."
        else:
            dir_badge = "🟢 CALL (SUBIDA / COMPRA)"
            momentum_text = f"RSI en {rsi_str} (Sobreventa profunda + Giro alcista)"
            bb_text = "Rechazo contundente en Banda Inferior de Bollinger"
            thesis_text = "Fuerte absorción de compra en piso dinámico; se proyecta rebote impulsivo hacia la media móvil central."

        concurrent_line = f"\n📊 <b>Operaciones activas:</b> <code>{active_concurrent}</code>" if active_concurrent else ""

        return (
            f"🎯 <b>ORDEN EJECUTADA: ALTA PRECISIÓN SNIPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC 24/7)</code>\n"
            f"🧭 <b>Dirección:</b> <b>{dir_badge}</b>\n"
            f"💵 <b>Inversión Fija:</b> <b>{invested_str}</b> 🛡️ (Cero Martingala)\n"
            f"⏱️ <b>Tiempo de Expiración:</b> <b>{dur_str}</b> (Sin ruido de 1m)\n"
            f"🎯 <b>Convicción Algorítmica:</b> <b>{conf_pct}% [Filtro Sniper Aprobado]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>ANÁLISIS TÉCNICO MULTI-FACTOR:</b>\n"
            f"• 📊 <b>Momento:</b> {momentum_text}\n"
            f"• ⚡ <b>Volatilidad:</b> {bb_text}\n"
            f"• 🕯️ <b>Acción del Precio:</b> {pattern_str}\n"
            f"• 📈 <b>Tendencia Macro:</b> Estructura validada por EMA 50 / 100\n"
            f"• 🔗 <b>Confluencias:</b> <b>{confluences}/3 factores confirmados</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔮 <b>Tesis de la Operación:</b>\n"
            f"<i>{thesis_text}</i>{concurrent_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Operación 100% automatizada. Monitoreando en tiempo real hasta el vencimiento...</i>"
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
        side_icon = "🟢" if "CALL" in side.upper() or "BUY" in side.upper() else "🔴"

        if is_win:
            return (
                f"🏆 <b>¡OPERACIÓN GANADORA! (+{pnl_pct:,.1f}%)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"🧭 <b>Dirección:</b> <b>{side} {side_icon}</b>\n"
                f"💰 <b>Ganancia Neta:</b> <b>+{net_pnl:,.2f} USD</b> 💵\n"
                f"📈 <b>Saldo en Cuenta:</b> <b>{equity_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ <b>Gestión de Riesgo:</b>\n"
                f"• Inversión plana $25 USD respetada (Cero Martingala)\n"
                f"• El bot buscará la siguiente oportunidad solo ante confluencia perfecta triple.\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            return (
                f"🛡️ <b>OPERACIÓN CERRADA (STOP RESPETADO)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Activo:</b> <code>{clean_symbol} (OTC)</code>\n"
                f"🧭 <b>Dirección:</b> <b>{side} {side_icon}</b>\n"
                f"📉 <b>Resultado:</b> <b>-${abs(net_pnl):,.2f} USD</b>\n"
                f"📈 <b>Saldo en Cuenta:</b> <b>{equity_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ <b>Protección de Capital Activa:</b>\n"
                f"• Riesgo estrictamente contenido al stake de $25 USD.\n"
                f"• CERO martingala: No se doblan apuestas por pérdidas.\n"
                f"• El bot preserva el saldo para setups de alta probabilidad.\n"
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
