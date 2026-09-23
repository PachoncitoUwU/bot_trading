"""FastAPI Server Entrypoint with Background Trading Loop, Telegram Integration, and WebSocket."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path regardless of execution CWD
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.config import settings
from app.core.logger import logger
from app.api.routes_bot import router as bot_router
from app.api.websocket_hub import ws_hub
from app.engine.bot_runner import bot_runner
from app.database.session import init_db, close_db
from app.telegram.telegram_client import init_telegram_client
from app.core.power_manager import enable_24_7_execution_mode, disable_24_7_execution_mode

# Background task references
_trading_task: asyncio.Task = None
_heartbeat_task: asyncio.Task = None
_polling_task: asyncio.Task = None


# ──────────────────────────────────────────────────────────────────────────────
# Background loops
# ──────────────────────────────────────────────────────────────────────────────

async def trading_background_loop():
    """Continuous 5-second trading tick loop with automated daily market schedule."""
    logger.info("[SERVER] Background trading loop started.")
    while True:
        try:
            if hasattr(bot_runner, "check_daily_market_schedule"):
                await bot_runner.check_daily_market_schedule()
            if bot_runner.is_running:
                await bot_runner.tick()
        except Exception as e:
            logger.error(f"[SERVER] Error in trading loop tick: {e}", exc_info=True)
        await asyncio.sleep(5)


async def heartbeat_loop(telegram_client):
    """Sends a Telegram heartbeat every TELEGRAM_HEARTBEAT_MINUTES minutes. (GAP #3 fix)"""
    interval_seconds = settings.TELEGRAM_HEARTBEAT_MINUTES * 60
    logger.info(
        f"[HEARTBEAT] Scheduler started. Interval: {settings.TELEGRAM_HEARTBEAT_MINUTES} min."
    )
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            msg = bot_runner.heartbeat.format_heartbeat_message(
                mode=bot_runner.mode,
                circuit_status=bot_runner.circuit_breaker.status,
                equity=bot_runner.equity,
                active_positions_count=len(bot_runner.risk_manager.active_positions),
                is_reconciled=not bot_runner.reconciler.is_locked_for_review,
            )
            await telegram_client.send_message(settings.TELEGRAM_ADMIN_CHAT_ID, msg)
            logger.info(
                f"[HEARTBEAT] Sent to admin chat {settings.TELEGRAM_ADMIN_CHAT_ID}. "
                f"Next in {settings.TELEGRAM_HEARTBEAT_MINUTES} min."
            )
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to send heartbeat: {e}", exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# App Lifespan
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _trading_task, _heartbeat_task, _polling_task

    # 0. Prevent Windows from sleeping (keep CPU, Network & Bot active 24/7)
    enable_24_7_execution_mode()

    # 1. Initialize database — create all tables if they don't exist (GAP #4 fix)
    await init_db()

    # 2. Initialize Telegram client (GAP #2 fix)
    telegram_client = init_telegram_client()

    # 3. Auto-start trading engine and sync real exchange balance
    try:
        await bot_runner.start()
    except Exception as e:
        logger.error(f"[SERVER] Error initializing bot_runner on startup: {e}")
    _trading_task = asyncio.create_task(trading_background_loop())

    # 4. Launch heartbeat scheduler if Telegram is configured (GAP #3 fix)
    if telegram_client and settings.TELEGRAM_ADMIN_CHAT_ID:
        _heartbeat_task = asyncio.create_task(heartbeat_loop(telegram_client))

        # Send startup notification with interactive keyboard
        keyboard = bot_runner.admin_handler.get_main_menu_keyboard()
        status_header = (
            f"🟢 <b>BOT CONECTADO Y OPERANDO 24/7 ({settings.BOT_MODE.value})</b>"
            if bot_runner.is_running
            else f"🟡 <b>BOT CONECTADO EN MODO STANDBY ({settings.BOT_MODE.value})</b>"
        )
        status_footer = (
            "<i>El bot ya está escaneando el mercado y buscando entradas activamente en la nube.</i>"
            if bot_runner.is_running
            else "<i>Para comenzar a operar, presiona el botón:</i> <b>▶️ Iniciar Trading</b>"
        )
        await telegram_client.send_message(
            settings.TELEGRAM_ADMIN_CHAT_ID,
            f"{status_header}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Exchange: <code>{settings.EXCHANGE_ID.upper()}</code>\n"
            f"Saldo actual: <b>${bot_runner.equity:,.2f} USD</b>\n"
            f"🎯 <b>Meta programada:</b> +3.5% (Asegura ganancia y se apaga)\n"
            f"🛡️ <b>Freno Stop Loss:</b> -3.0% (Protección de capital)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_footer}",
            reply_markup=keyboard
        )

    # 5. Launch Telegram polling loop (GAP #2 fix)
    if telegram_client:
        from app.telegram.polling_loop import TelegramPollingLoop
        polling_loop = TelegramPollingLoop(telegram_client)
        _polling_task = asyncio.create_task(polling_loop.start())

    logger.info(
        f"[SERVER] Trading Bot API ready on port {settings.PORT} ({settings.APP_ENV})"
    )

    yield  # ── Application running ──────────────────────────────────────────

    # Shutdown sequence
    for task in (_polling_task, _heartbeat_task, _trading_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    await bot_runner.exchange.close()
    await close_db()

    if telegram_client:
        await telegram_client.close()

    # Restore standard Windows power behavior
    disable_24_7_execution_mode()

    logger.info("[SERVER] Trading Bot API successfully shut down.")


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Institutional Trading Bot API",
    description="Multi-Exchange Trading Engine with Telegram Hub, Decimal Precision and Risk Controls",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bot_router)

# ──────────────────────────────────────────────────────────────────────────────
# WebSocket
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keepalive / incoming browser commands
    except WebSocketDisconnect:
        ws_hub.disconnect(websocket)
    except Exception as e:
        # GAP silent exception #3 fix: distinguish network disconnects from server bugs
        logger.warning(
            f"[WEBSOCKET] Unexpected error, disconnecting client: "
            f"{type(e).__name__}: {e}"
        )
        ws_hub.disconnect(websocket)


# ──────────────────────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "mode": settings.BOT_MODE.value,
        "exchange": settings.EXCHANGE_ID,
        "is_running": bot_runner.is_running,
        "telegram_enabled": bool(settings.TELEGRAM_BOT_TOKEN),
        "db_initialized": True,
    }


# Mount Frontend static files at the end so it doesn't intercept API routes
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    import sys
    reload_enabled = bool(sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty())
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=reload_enabled)
