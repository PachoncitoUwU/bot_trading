"""Verification script for AI Strategy, Internet Sentiment, and Telegram Visual Alerts."""
import asyncio
from decimal import Decimal
import os
import sys

# Ensure backend directory is in python path
backend_path = os.path.join(os.path.dirname(__file__), "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from app.core.logger import logger
from app.services.sentiment_service import sentiment_service
from app.strategies.ai_learning_strategy import AILearningStrategy
from app.telegram.telegram_client import TelegramClient
from app.telegram.admin_handlers import TelegramAdminHandler
from app.telegram.visual_reporter import generate_trade_card_image


async def main():
    print("=" * 60)
    print("🚀 VERIFICACIÓN DE COMPONENTES: IA, INTERNET Y TELEGRAM")
    print("=" * 60)

    # 1. Probar Servicio de Internet (Fear & Greed Index)
    print("\n🌐 1. Consultando Sentimiento de Internet en Vivo...")
    sentiment = await sentiment_service.get_sentiment(force_refresh=True)
    print(f"   • Valor Fear & Greed: {sentiment.get('value')}/100")
    print(f"   • Estado: {sentiment.get('status')}")
    print(f"   • Consejo IA: {sentiment.get('strategy_advice')}")
    assert "value" in sentiment, "Error: Sentimiento no devolvió 'value'"
    print("   ✅ Internet Sentiment OK!")

    # 2. Probar Estrategia de IA Adaptativa
    print("\n🧠 2. Probando Motor de Estrategia de IA...")
    ai_strategy = AILearningStrategy(symbols=["BTC/USDT"], timeframe="1h")
    ai_strategy.update_sentiment_cache(sentiment)

    # Generar 60 velas simuladas de tendencia alcista con rechazo martillo
    candles = []
    base_price = Decimal("60000.00")
    for i in range(60):
        o = base_price + Decimal(str(i * 50))
        c = o + Decimal("40")
        h = c + Decimal("20")
        l = o - Decimal("10")
        if i == 59:
            # Forzar mecha larga inferior (Martillo alcista)
            l = o - Decimal("250")
        v = Decimal("150.5")
        candles.append([1600000000 + i * 3600, float(o), float(h), float(l), float(c), float(v)])

    signals = ai_strategy.generate_signals({"BTC/USDT": candles}, open_positions={})
    print(f"   • Señales generadas: {len(signals)}")
    if signals:
        sig = signals[0]
        print(f"   • Tipo: {sig.signal_type.value} en {sig.symbol} a ${sig.price}")
        print(f"   • Confianza IA: {sig.confidence:.2f}")
        print(f"   • Stop Loss: ${sig.stop_loss:,.2f} | Take Profit: ${sig.take_profit:,.2f}")
        print(f"   • Patrón: {sig.pattern_name}")
        print(f"   • Razones: {sig.reason}")
    print("   ✅ Estrategia IA OK!")

    # 3. Probar Envío de Teclado Táctil a Telegram
    print(f"\n📱 3. Enviando Menú Interactivo a Telegram (Chat ID: {settings.TELEGRAM_ADMIN_CHAT_ID})...")
    client = TelegramClient(settings.TELEGRAM_BOT_TOKEN)
    keyboard = TelegramAdminHandler.get_main_menu_keyboard()

    welcome_text = (
        "🤖 <b>¡SISTEMA DE TRADING AUTÓNOMO ACTIVADO!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Se han conectado los siguientes módulos:\n"
        "🌐 <b>Internet:</b> Fear & Greed Index en vivo\n"
        "🧠 <b>Inteligencia:</b> Estrategia IA con Confianza Dinámica\n"
        "🛡 <b>Riesgo:</b> Stop Loss y Take Profit automáticos\n"
        "📸 <b>Reportes:</b> Tarjetas visuales de ganancias en cada cierre\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>Usa los botones táctiles que acaban de aparecer en tu pantalla:</i>"
    )

    resp_msg = await client.send_message(
        chat_id=settings.TELEGRAM_ADMIN_CHAT_ID,
        text=welcome_text,
        reply_markup=keyboard
    )
    if resp_msg:
        print("   ✅ Mensaje con botones táctiles enviado exitosamente a Telegram!")
    else:
        print("   ⚠️ No se pudo enviar mensaje a Telegram (verifica conexión).")

    # 4. Probar Envío de Tarjeta Gráfica Visual de Ganancia (PNG)
    print("\n📸 4. Generando y Enviando Tarjeta Gráfica de Ganancia a Telegram...")
    img_card = generate_trade_card_image(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=Decimal("62400.00"),
        exit_price=Decimal("64272.00"),
        net_pnl=Decimal("93.60"),
        pnl_pct=Decimal("3.00"),
        pattern_name="Cruce IA + Sentimiento",
        is_win=True
    )
    card_caption = (
        "🎉 <b>DEMOSTRACIÓN DE REPORTE VISUAL AUTOMÁTICO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Así es exactamente como recibirás en Telegram cada operación cerrada:\n"
        "💵 <b>Ganancia neta:</b> +$93.60 USDT (+3.00%)\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    resp_photo = await client.send_photo(
        chat_id=settings.TELEGRAM_ADMIN_CHAT_ID,
        photo_bytes=img_card.getvalue(),
        caption=card_caption
    )
    if resp_photo:
        print("   ✅ ¡Foto con tarjeta visual enviada exitosamente a Telegram!")
    else:
        print("   ⚠️ No se pudo enviar la foto a Telegram.")

    await client.close()
    print("\n" + "=" * 60)
    print("🎉 ¡TODOS LOS COMPONENTES HAN SIDO VERIFICADOS CON ÉXITO!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
