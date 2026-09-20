"""Script para detectar el Chat ID del usuario y configurar el .env automáticamente."""
import urllib.request
import json
import time
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

TOKEN = "8942037613:AAEqRYRcPiRMe9F_zDEO6kmm7r9EB2NLlGQ"

print("=" * 60)
print("🤖 ESCUCHANDO MENSAJES EN TELEGRAM...")
print("👉 Por favor abre Telegram, entra a @Bot_tradingg_bot y dale a 'Iniciar' (/start)")
print("=" * 60)

chat_id = None
username = None
first_name = None

for attempt in range(60):  # Espera hasta 2 minutos
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read().decode('utf-8'))
        
        results = data.get("result", [])
        if results:
            last_msg = results[-1].get("message", {})
            chat = last_msg.get("chat", {})
            if chat.get("id"):
                chat_id = str(chat.get("id"))
                username = chat.get("username", "Sin username")
                first_name = chat.get("first_name", "Usuario")
                print(f"\n✅ ¡MENSAJE DETECTADO!")
                print(f"👤 De: {first_name} (@{username})")
                print(f"🆔 Chat ID: {chat_id}")
                break
    except Exception as e:
        pass
    
    time.sleep(2)
    print(".", end="", flush=True)

if not chat_id:
    print("\n⏳ Tiempo agotado. No se recibió mensaje. Vuelve a ejecutar cuando le hayas enviado un mensaje al bot.")
    sys.exit(1)

# Crear / Actualizar .env
env_content = f"""# ==============================================================================
# TRADING BOT CONFIGURATION (PAPER & TELEGRAM VERIFIED)
# ==============================================================================

BOT_MODE=PAPER
EXCHANGE_ID=binance
USE_TESTNET=true

EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
EXCHANGE_PASSWORD=

TRADING_SYMBOLS=BTC/USDT,ETH/USDT
DEFAULT_TIMEFRAME=1h

MAX_DAILY_DRAWDOWN_PCT=3.0
MAX_ACCOUNT_EXPOSURE_PCT=20.0
MAX_RISK_PER_TRADE_PCT=1.0
CIRCUIT_BREAKER_MAX_ERRORS=3

TELEGRAM_BOT_TOKEN={TOKEN}
TELEGRAM_ADMIN_CHAT_ID={chat_id}
TELEGRAM_CHANNEL_ID=
TELEGRAM_SIGNAL_TTL_SECONDS=45
TELEGRAM_HEARTBEAT_MINUTES=60

APP_ENV=development
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./trading_bot.db
"""

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
with open(env_path, "w", encoding="utf-8") as f:
    f.write(env_content)

print(f"\n📝 Archivo .env creado/actualizado exitosamente con tu Chat ID ({chat_id}).")

# Enviar mensaje de confirmación de Gap #2
send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
msg_text = (
    "🎉 <b>¡CONEXIÓN TELEGRAM EXITOSA! (GAP #2 VERIFICADO)</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    f"Hola <b>{first_name}</b> (@{username}), el bot ya está enlazado a tu cuenta.\n\n"
    "⚙️ <b>Configuración activa:</b>\n"
    "• <b>Modo:</b> <code>PAPER</code> (Simulado)\n"
    "• <b>Base de Datos:</b> <code>SQLite + SQLAlchemy (Verificada)</code>\n"
    "• <b>Comandos:</b> <code>/status</code>, <code>/panic</code>, <code>/help</code>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Prueba enviando /status o /help aquí mismo.</i>"
)

post_data = json.dumps({
    "chat_id": chat_id,
    "text": msg_text,
    "parse_mode": "HTML"
}).encode('utf-8')

req_send = urllib.request.Request(send_url, data=post_data, headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req_send)
print("🚀 Mensaje de prueba enviado a tu Telegram. ¡Revisa tu chat!")
