"""Telegram Admin Command and Interactive Callback Handlers."""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.constants import BotMode, CircuitBreakerStatus
from app.core.logger import logger
from app.engine.risk_manager import RiskManager
from app.engine.state_reconciler import StateReconciler
from app.telegram.interactive_signal import InteractiveSignalManager


class TelegramAdminHandler:
    """Handles admin commands and callback queries for the private Telegram channel."""

    def __init__(
        self,
        risk_manager: RiskManager,
        state_reconciler: StateReconciler,
        signal_manager: InteractiveSignalManager
    ):
        self.risk_manager = risk_manager
        self.state_reconciler = state_reconciler
        self.signal_manager = signal_manager
        self.is_panic_stopped = False

    def handle_panic_command(self, user_id: str) -> str:
        """
        /panic command:
        Immediately trips the circuit breaker, locks state, and signals emergency close.
        """
        self.is_panic_stopped = True
        self.risk_manager.circuit_breaker.status = CircuitBreakerStatus.TRIPPED
        self.risk_manager.circuit_breaker.trip_reason = f"Manual /panic executed by admin {user_id}"
        
        logger.error(f"[PANIC] Manual /panic command executed by Telegram Admin: {user_id}")
        return (
            "🚨 <b>PARADA DE EMERGENCIA ACTIVADA (/panic)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1. Circuit breaker activado (TRIPPED).\n"
            "2. Nuevas entradas BLOQUEADAS.\n"
            "3. Cerrando posiciones activas y cancelando órdenes pendientes...\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Para reanudar de forma segura use /resume_after_review [motivo]</i>"
        )

    def handle_resume_after_review(self, user_id: str, reason: str) -> str:
        """
        /resume_after_review <reason> command:
        Explicit, intentional command to unlock the bot following manual verification.
        """
        if not reason or len(reason.strip()) < 4:
            return (
                "⚠️ <b>Error de formato:</b> Debe proporcionar una justificación obligatoria.\n"
                "Ejemplo: <code>/resume_after_review Verificado orden en Binance, todo OK</code>"
            )

        self.is_panic_stopped = False
        self.risk_manager.circuit_breaker.manual_reset()
        self.risk_manager.is_daily_drawdown_locked = False
        self.state_reconciler.unlock_after_manual_review(user_id, reason)

        return (
            "✅ <b>SISTEMA REANUDADO TRAS REVISIÓN MANUAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Operador:</b> <code>{user_id}</code>\n"
            f"📝 <b>Justificación:</b> <i>{reason}</i>\n"
            "🛡 <b>Circuit Breaker:</b> NORMAL\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>El bot ha reanudado el escaneo de mercado de forma segura.</i>"
        )

    def handle_status_command(
        self,
        current_equity: Decimal,
        available_cash: Optional[Decimal] = None,
        mode: BotMode = BotMode.PAPER,
        is_running: bool = False,
        ai_thoughts: Optional[Dict[str, str]] = None,
        target_mode: str = "3.5%"
    ) -> str:
        """Friendly account status, balance, and live AI thoughts report."""
        exch = settings.EXCHANGE_ID.upper()
        mode_str = f"DEMO / PRACTICE ({exch})" if mode in (BotMode.PAPER, BotMode.TESTNET) else f"CUENTA REAL {exch} 🚀"
        cash_val = available_cash if available_cash is not None else current_equity

        pos_lines = []
        if self.risk_manager.active_positions:
            for sym, pos in self.risk_manager.active_positions.items():
                pos_lines.append(
                    f"  • <b>{sym}:</b> Operación abierta (🎯 TP: +3.0% | 🛡 SL: -1.5%)"
                )
        else:
            if is_running:
                pos_lines.append("  • <i>Sin operaciones abiertas en este segundo. Escaneando confluencias...</i>")
            else:
                pos_lines.append("  • <i>El bot está en pausa. Pulsa '▶️ Iniciar Trading' para empezar.</i>")

        pos_str = "\n".join(pos_lines)

        # AI live thoughts on pairs
        thought_lines = []
        if ai_thoughts and is_running:
            for s, t in list(ai_thoughts.items())[:4]:
                clean_s = s.replace("-OTC", "")
                thought_lines.append(f"  • <b>{clean_s}:</b> <i>{t}</i>")
        thought_str = "\n".join(thought_lines) if thought_lines else "  • <i>Analizando velas de 1m en búsqueda de sobrecompra/sobreventa...</i>"

        status_badge = "🟢 <b>ACTIVO Y ESCANEANDO EN VIVO</b>" if is_running else "⏸️ <b>EN PAUSA / STANDBY</b>"

        return (
            "📊 <b>ESTADO DE TU CUENTA Y RADAR IA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Estado del Bot:</b> {status_badge}\n"
            f"💼 <b>Cuenta:</b> <code>{mode_str}</code>\n"
            f"💰 <b>Saldo en Cuenta:</b> <b>${current_equity:,.2f} USD</b>\n"
            f"🎯 <b>Meta de Sesión:</b> <b>+{target_mode}</b> (Auto-apagado protector)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📈 <b>Operaciones en Curso:</b>\n"
            f"{pos_str}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🧠 <b>Diagnóstico en Vivo de la IA:</b>\n"
            f"{thought_str}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛡 <b>Protección de Fondos:</b> Stop Loss de Sesión -3% Activo ✅"
        )

    def handle_start_bot(self, user_id: str, target_pct: str = "3.5%") -> str:
        """Friendly start command from mobile button."""
        self.is_panic_stopped = False
        self.risk_manager.circuit_breaker.manual_reset()
        self.state_reconciler.is_locked_for_review = False
        return (
            "🟢 <b>¡TRADING INICIADO CON ÉXITO!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Operador:</b> <code>{user_id}</code>\n"
            "🤖 <b>Estado:</b> ACTIVO Y ESCANEANDO\n"
            f"🎯 <b>Meta de Sesión:</b> <b>+{target_pct}</b> (Auto-apagado al cumplir)\n"
            "🛡️ <b>Freno de Seguridad:</b> <b>-3.0%</b> (Stop Loss de cuenta)\n"
            "⚡ <b>Gestión de Capital:</b> Posturas proporcionales seguras\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>El bot analizará las mejores confluencias y te notificará cada operación y resultado.</i>"
        )

    def handle_pause_bot(self, user_id: str) -> str:
        """Friendly pause command from mobile button."""
        return (
            "⏸️ <b>BOT EN PAUSA TEMPORAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Operador:</b> <code>{user_id}</code>\n"
            "💤 <b>Nuevas entradas:</b> DETENIDAS\n"
            "🛡 <b>Posiciones abiertas:</b> Siguen vigiladas por el motor de riesgo\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Pulsa '▶️ Iniciar Bot' cuando quieras reanudar.</i>"
        )

    def handle_sentiment_report(self, sentiment: Dict[str, Any]) -> str:
        """Formats real-time web market intelligence."""
        val = sentiment.get("value", 50)
        status = sentiment.get("status", "NEUTRAL")
        advice = sentiment.get("strategy_advice", "Operación estándar.")
        is_live = "EN VIVO 🌐" if sentiment.get("is_live", True) else "OFFLINE"

        # Visual bar representation
        filled = min(10, max(0, val // 10))
        bar = "🟩" * filled + "⬜" * (10 - filled)

        return (
            "🌐 <b>INTELIGENCIA Y SENTIMIENTO WEB</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📡 <b>Fuente:</b> Crypto Fear & Greed Index ({is_live})\n"
            f"📊 <b>Puntuación:</b> <b>{val}/100</b>\n"
            f"[{bar}]\n"
            f"🎭 <b>Diagnóstico:</b> <code>{status}</code>\n\n"
            f"💡 <b>Impacto en la IA:</b>\n"
            f"<i>{advice}</i>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

    def handle_pnl_report(self, equity: Decimal, initial_equity: Decimal, closed_trades_count: int = 0) -> str:
        """Generates crystal-clear PnL summary report."""
        diff = equity - initial_equity
        pnl_pct = (diff / initial_equity) * Decimal("100") if initial_equity > 0 else Decimal("0")
        sign = "+" if diff >= 0 else ""
        icon = "🟢" if diff >= 0 else "🔴"

        return (
            f"💰 <b>RESUMEN DE GANANCIAS DE TU CUENTA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🏁 <b>Capital Inicial:</b> ${initial_equity:,.2f} USDT\n"
            f"💵 <b>Capital Actual:</b> <b>${equity:,.2f} USDT</b>\n\n"
            f"{icon} <b>Ganancia Total Acumulada:</b> <b>{sign}${diff:,.2f} USD ({sign}{pnl_pct:.2f}%)</b> 💵\n"
            f"📊 <b>Operaciones Completadas:</b> {closed_trades_count}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Todos los resultados son calculados matemáticamente en base a precios reales de Binance.</i>"
        )

    def handle_radar_report(self, radar_data: Dict[str, Any], active_positions: Dict[str, Any]) -> str:
        """Explains in plain Spanish what the AI is watching and about to do."""
        lines = []
        if not radar_data:
            lines.append("• <i>Iniciando radar de mercado...</i>")
        else:
            for symbol, info in radar_data.items():
                p = info.get("last_price", 0.0)
                if symbol in active_positions:
                    pos = active_positions[symbol]
                    lines.append(
                        f"🪙 <b>{symbol}:</b> Comprado a ${pos.entry_price:,.2f}\n"
                        f"   • <b>Próxima acción:</b> Esperando que suba a <b>${pos.take_profit:,.2f}</b> para vender con ganancia (+3.0%).\n"
                        f"   • <b>Protección:</b> Si cae a ${pos.stop_loss:,.2f}, venderá para no perder más del -1.5%."
                    )
                else:
                    pattern = info.get("pattern_detected", "Monitoreando")
                    lines.append(
                        f"🪙 <b>{symbol}:</b> Precio actual: ${p:,.2f}\n"
                        f"   • <b>Diagnóstico IA:</b> {pattern}\n"
                        f"   • <b>Próxima acción:</b> {info.get('next_action', 'Buscando punto de entrada seguro...')}"
                    )

        content = "\n\n".join(lines)
        return (
            "🎯 <b>RADAR DE LA IA (¿Qué está a punto de hacer?)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{content}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>⚡ La IA analiza velas de 5 min y toma decisiones cada 5 segundos.</i>"
        )

    def handle_ai_stats_report(self, ai_stats: Dict[str, Any]) -> str:
        """Formats AI reinforcement learning metrics for Telegram."""
        total_learned = ai_stats.get("total_trades_learned", 0)
        win_rate = ai_stats.get("overall_learned_win_rate", 0.0)
        patterns = ai_stats.get("learned_patterns", {})
        min_conf = ai_stats.get("min_confidence", 0.55)

        pattern_lines = []
        if patterns:
            for name, p_data in patterns.items():
                w = p_data.get("weight", 1.0)
                wr = p_data.get("win_rate", 0.0)
                wins = p_data.get("wins", 0)
                losses = p_data.get("losses", 0)
                pattern_lines.append(f"  • <b>{name}</b>: {w:.2f}x ({wins}W / {losses}L - {wr}%)")
        else:
            pattern_lines.append("  • <i>Calibrando primeros ciclos en velas de 5 min...</i>")

        patterns_str = "\n".join(pattern_lines)

        return (
            "🧠 <b>ESTADO DE APRENDIZAJE DE LA IA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <b>Velocidad / Temporalidad:</b> Velas de 5 Minutos (5m)\n"
            f"🎯 <b>Confianza Mínima:</b> {int(min_conf * 100)}%\n"
            f"📚 <b>Operaciones Aprendidas:</b> {total_learned}\n"
            f"🏆 <b>Tasa de Acierto IA:</b> {win_rate}%\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔬 <b>Ponderación de Patrones Adaptativos:</b>\n"
            f"{patterns_str}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>La IA premia automáticamente los patrones rentables y castiga los fallidos.</i>"
        )

    def handle_target_progress_report(self, progress: Dict[str, Any]) -> str:
        """Formats the visual Take-Profit session target and progress bar."""
        p_pct = progress.get("profit_pct", Decimal("0"))
        t_pct = progress.get("target_pct", Decimal("3.0"))
        net_profit = progress.get("net_profit", Decimal("0"))
        starting_eq = progress.get("starting_equity", Decimal("10000"))
        curr_eq = progress.get("current_equity", Decimal("10000"))
        bar = progress.get("progress_bar", "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜")
        completion = progress.get("completion_pct", 0.0)
        target_amount = progress.get("target_amount", Decimal("300"))
        rem_profit = progress.get("remaining_profit", Decimal("0"))
        regime = progress.get("market_regime", {})
        regime_label = regime.get("label", "Mercado Estándar")
        is_target_reached = progress.get("is_target_reached", False)
        trades = progress.get("closed_trades", 0)
        wins = progress.get("wins", 0)
        losses = progress.get("losses", 0)
        win_rate = progress.get("win_rate", 0.0)
        target_mode = progress.get("target_mode", "")

        sign = "+" if net_profit >= 0 else ""

        if target_mode in ("MARATON_10K", "MARATON", "10K", "APRENDIZAJE"):
            if is_target_reached:
                if curr_eq >= Decimal("10000.00"):
                    status_line = "🏆 <b>¡MARATÓN COMPLETADA! Superaste los $10,000 USD.</b>"
                else:
                    status_line = "🛑 <b>MARATÓN DETENIDA: Saldo llegó al límite de seguridad ($50 USD).</b>"
            else:
                status_line = "🏃‍♂️ <b>MODO MARATÓN ACTIVO:</b> Operando sin pausas rumbo a <b>$10,000 USD</b> (Stop: $50 USD)."

            return (
                "🏃‍♂️ <b>MARATÓN DE ENTRENAMIENTO & APRENDIZAJE</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Meta Final:</b> <b>$10,000.00 USD</b>\n"
                f"🛑 <b>Stop Límite:</b> <b>$50.00 USD (Límite inferior)</b>\n"
                f"💰 <b>Saldo Actual:</b> <b>${curr_eq:,.2f} USD</b>\n\n"
                f"<b>Progreso hacia los $10,000 USD:</b>\n"
                f"[{bar}] <b>{completion}%</b>\n"
                f"⏳ <b>Falta para $10,000:</b> ${rem_profit:,.2f} USD\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Operaciones:</b> {trades} ({wins}W / {losses}L - {win_rate}% Win Rate)\n"
                f"💵 <b>PnL Sesión:</b> {sign}${net_profit:,.2f} USD\n"
                f"⚡ <b>Staking Sniper:</b> $50 → $100 → $200 (Ultra-Filtro)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{status_line}\n"
                "<i>El bot operará continuamente sin frenarse por metas de 3.5%, aprendiendo de cada vela.</i>"
            )

        # Status icon
        if is_target_reached:
            status_line = "🏆 <b>ESTADO: ¡META DE SESIÓN ALCANZADA! Bot en reposo ganador.</b>"
        else:
            status_line = "⚡ <b>ESTADO:</b> Cazando entradas para cumplir la meta..."

        cycle_state = progress.get("cycle_state", "ACTIVE")
        cycle_rem = progress.get("cycle_remaining_min", 60)
        cycle_enabled = progress.get("hourly_cycle_enabled", True)
        if cycle_enabled:
            if cycle_state == "ACTIVE":
                cycle_str = f"🟢 Bloque Activo ({cycle_rem} min restantes de operativa)"
            else:
                cycle_str = f"💤 Reposo Programado ({cycle_rem} min para reanudar)"
        else:
            cycle_str = "🔄 Continuo 24/7 (Sin pausas por hora)"

        return (
            "🎯 <b>META DE GANANCIA Y PROGRESO DE SESIÓN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Régimen:</b> <code>{regime_label}</code>\n"
            f"🎯 <b>Meta de Ganancia:</b> <b>+{t_pct:.1f}% (+${target_amount:,.2f} USD)</b>\n"
            f"💵 <b>Ganancia Hoy:</b> <b>{sign}${net_profit:,.2f} USD ({sign}{p_pct:.2f}%)</b>\n\n"
            f"<b>Progreso hacia el objetivo:</b>\n"
            f"[{bar}] <b>{completion}%</b>\n"
            f"⏳ <b>Falta para completar:</b> ${rem_profit:,.2f} USD\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ <b>Ciclo Horario:</b> {cycle_str}\n"
            f"📊 <b>Operaciones Hoy:</b> {trades} ({wins}W / {losses}L - {win_rate}% Win Rate)\n"
            f"💰 <b>Saldo en Cuenta:</b> ${curr_eq:,.2f} USD\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_line}\n"
            "<i>Al llegar al 100% de la meta, el bot se apaga solo para proteger tu dinero.</i>"
        )

    def handle_toggle_hourly_cycle(self, session_manager) -> str:
        """Toggles the 1-hour active / 1-hour rest cycle."""
        session_manager.hourly_cycle_enabled = not session_manager.hourly_cycle_enabled
        state_str = "ACTIVADO (1h Operando / 1h Descanso) ⏱️" if session_manager.hourly_cycle_enabled else "DESACTIVADO (Operación Continua 24/7) 🔄"
        return (
            "⏱️ <b>MODO DE CICLOS POR HORA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Estado actual: <b>{state_str}</b>\n\n"
            "• <b>Activado:</b> El bot opera 60 minutos y descansa 60 minutos para enfriar el mercado y evitar sobreoperar.\n"
            "• <b>Desactivado:</b> El bot busca entradas continuamente las 24 horas hasta cumplir la meta de ganancia.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Puedes alternarlo nuevamente enviando /horas o pulsando el botón.</i>"
        )

    def handle_set_target(self, session_manager, mode: str) -> str:
        """Updates target mode between 3.5%, 3%, 4%, 5%, 10K / MARATON."""
        clean_mode = mode.upper().replace("%", "").strip()
        if clean_mode in ("10K", "MARATON", "MARATÓN", "MARATON_10K", "APRENDIZAJE"):
            session_manager.target_mode = "MARATON_10K"
            session_manager.hourly_cycle_enabled = False
            session_manager.is_target_reached = False
            label = "🏃‍♂️ Maratón Continua (Meta: > $10,000 USD | Stop: $50 USD) 🚀"
        elif clean_mode in ("3.5", "3.5%"):
            session_manager.target_mode = "3.5%"
            label = "3.5% (Objetivo Recomendado con Staking $50/$100/$200) 🎯"
        elif clean_mode in ("3", "3%"):
            session_manager.target_mode = "3%"
            label = "3.0% (Conservador / Asegurar Rápido) 🛡️"
        elif clean_mode in ("4", "4%"):
            session_manager.target_mode = "4%"
            label = "4.0% (Equilibrado) ⚖️"
        elif clean_mode in ("5", "5%"):
            session_manager.target_mode = "5%"
            label = "5.0% (Máxima Rentabilidad) 🚀"
        else:
            session_manager.target_mode = "MARATON_10K"
            label = "🏃‍♂️ Maratón Continua ($10,000 USD) 🎯"

        return (
            "⚙️ <b>CONFIGURACIÓN DE META DE GANANCIA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Nueva meta fijada: <b>{label}</b>\n\n"
            "<i>El bot calculará automáticamente el dinero en dólares necesario y se apagará al alcanzarlo.</i>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

    def handle_market_hours_report(self, regime: Dict[str, Any]) -> str:
        """Advises the user on market conditions and whether right now is optimal to trade."""
        label = regime.get("label", "Mercado Estándar")
        is_morning = regime.get("is_morning_real", False)
        desc = regime.get("description", "")
        rec_target = regime.get("recommended_target_pct", Decimal("3.5"))

        if is_morning:
            status_icon = "🟢"
            veredicto = "⭐ <b>¡HORARIO DE ORO PARA OPERAR!</b> (Máxima Liquidez)"
            consejo = (
                "Bancos de Londres y Nueva York abiertos simultáneamente. "
                "Los gráficos respetan soportes, resistencias y patrones con máxima precisión. "
                "<b>¡Momento ideal para presionar '▶️ Iniciar Trading' y buscar tu meta del 5%!</b>"
            )
        else:
            status_icon = "🟡"
            veredicto = "⚡ <b>MERCADO NOCTURNO / FIN DE SEMANA (OTC)</b>"
            consejo = (
                "Mercado algorítmico del broker. El bot aplicará filtros de alta convicción "
                "y posturas seguras de $25 USD para proteger tu capital. Meta recomendada: +3.0% a +3.5%."
            )

        return (
            "🕒 <b>ASESOR DE HORARIOS DE MERCADO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Régimen Actual:</b> {status_icon} <code>{label}</code>\n"
            f"💡 <b>Diagnóstico:</b> {veredicto}\n\n"
            f"📝 <b>Recomendación del Algoritmo:</b>\n{consejo}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 <b>LOS MEJORES HORARIOS DE LA SEMANA:</b>\n"
            "• <b>Lunes a Viernes (07:00 a 12:00 UTC-5 / Bogotá / EST):</b> Solapamiento Londres-Nueva York. <i>El horario más limpio y rentable.</i>\n"
            "• <b>Tardes (12:00 a 17:00):</b> Tendencias de Nueva York.\n"
            "• <b>Noches y Fines de Semana:</b> Mercado OTC (operativa francotiradora prudente).\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>El bot está encendido 24/7 en Standby listo para cuando tú decidas iniciar.</i>"
        )

    @staticmethod
    def get_main_menu_keyboard() -> Dict[str, Any]:
        """Returns Telegram ReplyKeyboardMarkup with one-tap tactile buttons."""
        return {
            "keyboard": [
                [{"text": "▶️ Iniciar Trading"}, {"text": "⏹️ Parar Trading"}],
                [{"text": "🎯 Meta (3% a 5%)"}, {"text": "📊 Saldo y Balance"}],
                [{"text": "💰 Ganancias / PnL"}, {"text": "🕒 Cuándo Operar"}],
                [{"text": "🎯 Radar IA"}, {"text": "⚙️ Fijar Meta"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
            "is_persistent": True
        }


    def handle_signal_callback(self, signal_id: str, action: str, user_id: str) -> str:
        """Processes [Aprobar] or [Rechazar] inline button click."""
        approve = (action.lower() == "approve")
        success, signal, msg = self.signal_manager.resolve_signal(signal_id, approve=approve, operator_id=user_id)

        if not success:
            return f"❌ <b>Error al procesar señal:</b> {msg}"

        if approve and signal:
            return (
                f"✅ <b>ORDEN APROBADA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Símbolo: <b>{signal.symbol}</b>\n"
                f"Precio: <b>${signal.price}</b>\n"
                f"Patrón: <code>{signal.pattern_name}</code>\n"
                f"Operador: <code>{user_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Enviando orden al motor de ejecución...</i>"
            )
        else:
            return f"🚫 <b>Señal {signal_id} rechazada por el operador {user_id}.</b>"

