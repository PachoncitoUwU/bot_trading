"""Send test entry chart card to Telegram to verify live delivery."""
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.core.config import settings
from app.telegram.telegram_client import TelegramClient
from app.telegram.visual_reporter import generate_entry_chart_card


async def send_test_entry_card():
    if not settings.TELEGRAM_BOT_TOKEN:
        print("[SKIP] No TELEGRAM_BOT_TOKEN configured.")
        return
    client = TelegramClient(settings.TELEGRAM_BOT_TOKEN)
    target_chat = settings.TELEGRAM_CHANNEL_ID or settings.TELEGRAM_ADMIN_CHAT_ID
    if not target_chat:
        print("[SKIP] No target chat configured.")
        return

    # Generate 25 realistic 1m candles
    base_price = 1.0820
    candles = []
    for i in range(25):
        o = base_price + (i * 0.00015)
        h = o + 0.00025
        l = o - 0.00020
        c = o + 0.00018 if i % 2 == 0 else o - 0.00008
        candles.append([1700000000000 + i * 60000, o, h, l, c, 250])

    buf = generate_entry_chart_card(
        symbol="EURUSD-OTC",
        side="CALL",
        entry_price=Decimal("1.08550"),
        candles=candles,
        pattern_name="Martillo / Rechazo Alcista",
        reason="RSI en sobreventa (32.4) con rebote inminente y cruce rápido EMA 9 > 21",
        stake=Decimal("10.00"),
        mode_label="DEMO (IQ Option Práctica)"
    )

    caption = (
        "⚡ <b>¡NUEVA OPERACIÓN ABIERTA EN IQ OPTION!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🪙 <b>Activo:</b> <code>EURUSD-OTC</code>\n"
        "🧭 <b>Dirección:</b> <b>🟢 SUBIDA (CALL)</b>\n"
        "💵 <b>Inversión:</b> <b>$10.00 USD</b>\n"
        "📥 <b>Precio de Entrada:</b> <b>1.08550</b>\n"
        "⏱️ <b>Tiempo de Expiración:</b> <b>1 Minuto</b>\n\n"
        "🧠 <b>Patrón Técnico:</b> <code>Martillo / Rechazo Alcista</code>\n"
        "💡 <b>¿Por qué entró la IA?:</b>\n<i>RSI en sobreventa (32.4) con rebote inminente y cruce rápido EMA 9 > 21</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>📸 Gráfica adjunta con flecha indicando el punto de entrada.</i>"
    )

    await client.send_photo(chat_id=target_chat, photo_bytes=buf.getvalue(), caption=caption)
    await client.close()
    print("[SUCCESS] Live entry photo card sent to Telegram successfully!")


if __name__ == "__main__":
    asyncio.run(send_test_entry_card())
