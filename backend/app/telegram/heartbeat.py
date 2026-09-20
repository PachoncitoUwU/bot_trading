"""Heartbeat & Process Health Watchdog for Telegram."""
import os
import platform
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.constants import BotMode, CircuitBreakerStatus


class HeartbeatWatchdog:
    """Generates health telemetry and heartbeat status for Telegram."""

    def __init__(self):
        self.start_time = time.time()
        self.last_heartbeat_time = time.time()

    def get_uptime_str(self) -> str:
        elapsed = int(time.time() - self.start_time)
        return str(timedelta(seconds=elapsed))

    def format_heartbeat_message(
        self,
        mode: BotMode,
        circuit_status: CircuitBreakerStatus,
        equity: Decimal,
        active_positions_count: int,
        is_reconciled: bool
    ) -> str:
        """Constructs a clean Telegram heartbeat message."""
        status_icon = "🟢" if circuit_status == CircuitBreakerStatus.NORMAL and is_reconciled else "🔴"
        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        msg = (
            f"{status_icon} <b>BOT HEARTBEAT | ESTADO VITAL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <b>Uptime:</b> {self.get_uptime_str()}\n"
            f"📡 <b>Modo:</b> <code>{mode.value}</code>\n"
            f"💼 <b>Capital Actual:</b> ${equity:,.2f}\n"
            f"📊 <b>Posiciones Abiertas:</b> {active_positions_count}\n"
            f"🛡 <b>Circuit Breaker:</b> <code>{circuit_status.value.upper()}</code>\n"
            f"🔒 <b>Reconciliación:</b> {'OK' if is_reconciled else 'BLOQUEO DE REVISIÓN'}\n"
            f"🕒 <b>Fecha:</b> {now_utc}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Todo en orden. Sistema monitoreando el mercado.</i>"
        )
        return msg
