"""
GAP #2 EVIDENCE TEST — Telegram Real Message

Verifica que el TelegramClient envía un mensaje real a tu chat.
Corre en modo PAPER (sin exchange real).

Uso:
    cd backend
    python verify_telegram.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))


async def run():
    # Load settings
    from app.core.config import settings
    from app.telegram.telegram_client import TelegramClient

    print("=" * 55)
    print("GAP #2 EVIDENCE: TELEGRAM REAL MESSAGE")
    print("=" * 55)

    # Verify config is set
    if not settings.TELEGRAM_BOT_TOKEN:
        print("FAIL: TELEGRAM_BOT_TOKEN not set in .env")
        print("Set it and retry.")
        sys.exit(1)

    if not settings.TELEGRAM_ADMIN_CHAT_ID:
        print("FAIL: TELEGRAM_ADMIN_CHAT_ID not set in .env")
        sys.exit(1)

    print(f"Bot token: ...{settings.TELEGRAM_BOT_TOKEN[-6:]}")
    print(f"Admin chat ID: {settings.TELEGRAM_ADMIN_CHAT_ID}")
    print()

    client = TelegramClient(token=settings.TELEGRAM_BOT_TOKEN)

    # Send a real test message
    msg = (
        "✅ <b>TEST DE INTEGRACION — GAP #2</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "El TelegramClient esta conectado y enviando mensajes reales.\n"
        "Modo: <code>PAPER</code> (sin exchange real)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Si ves este mensaje, el Gap #2 tiene evidencia real.</i>"
    )

    result = await client.send_message(settings.TELEGRAM_ADMIN_CHAT_ID, msg)
    await client.close()

    if result:
        print("EVIDENCE: Message sent successfully.")
        print(f"  message_id: {result.get('message_id')}")
        print(f"  chat_id: {result.get('chat', {}).get('id')}")
        print(f"  date: {result.get('date')}")
        print()
        print("GAP #2 EVIDENCE CONFIRMED:")
        print("  Check your Telegram — you should have received the message.")
    else:
        print("FAIL: send_message returned None — check token and chat_id.")
        sys.exit(1)


asyncio.run(run())
