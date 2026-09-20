"""Session and Profit Target Manager with Hourly Cycles and Market Regime Detection."""
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from app.core.logger import logger


class SessionManager:
    """
    Manages session profit targets (Take-Profit de Sesión 3% - 5%),
    hourly working/resting cycles, and market regime awareness (Real Morning vs OTC).
    """

    def __init__(
        self,
        target_mode: str = "3.5%",  # "3%", "3.5%", "4%", "5%", "AUTO"
        hourly_cycle_enabled: bool = False,
        active_minutes: int = 60,
        rest_minutes: int = 60,
    ):
        self.target_mode: str = target_mode
        self.hourly_cycle_enabled: bool = hourly_cycle_enabled
        self.active_minutes: int = active_minutes
        self.rest_minutes: int = rest_minutes

        # Session Financials
        self.session_starting_equity: Decimal = Decimal("10000.00")
        self.current_equity: Decimal = Decimal("10000.00")
        self.session_net_profit: Decimal = Decimal("0.00")
        self.session_closed_trades: int = 0
        self.session_wins: int = 0
        self.session_losses: int = 0

        # Target State
        self.is_target_reached: bool = False
        self.target_reached_at: Optional[datetime] = None

        # Hourly Cycle State
        self.cycle_state: str = "ACTIVE"  # "ACTIVE" | "RESTING"
        self.cycle_start_time: float = time.time()
        self.session_start_time: datetime = datetime.now()

    def reset_session(self, current_equity: Optional[Decimal] = None) -> None:
        """Resets session stats, net profit, and clears target reached state."""
        if current_equity and current_equity > Decimal("0"):
            self.session_starting_equity = current_equity
            self.current_equity = current_equity
        elif self.current_equity > Decimal("0"):
            self.session_starting_equity = self.current_equity
        self.session_net_profit = Decimal("0.00")
        self.session_closed_trades = 0
        self.session_wins = 0
        self.session_losses = 0
        self.is_target_reached = False
        self.target_reached_at = None
        self.cycle_state = "ACTIVE"
        self.cycle_start_time = time.time()
        self.session_start_time = datetime.now()
        logger.info(f"[SESSION MANAGER] Session reset. Starting equity: ${self.session_starting_equity:,.2f} USD")

    def sync_starting_equity(self, equity: Decimal) -> None:
        """Sets or updates initial session equity on startup or reset."""
        if equity > Decimal("0"):
            self.session_starting_equity = equity
            self.current_equity = equity
            self.session_net_profit = Decimal("0.00")
            self.is_target_reached = False
            self.session_start_time = datetime.now()
            self.cycle_start_time = time.time()
            self.cycle_state = "ACTIVE"
            logger.info(f"[SESSION MANAGER] Session initialized. Starting equity: ${equity:,.2f} USD")

    def get_market_regime(self) -> Dict[str, Any]:
        """
        Determines if current time is Real Open Market Morning (Londres/NY overlap) or OTC/Off-hours.
        Peak real liquidity: Monday to Friday from 07:00 to 12:00 (EST / UTC-5).
        """
        now = datetime.now()
        weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        hour = now.hour

        # Weekend: OTC 100%
        if weekday in (5, 6):
            return {
                "regime": "OTC_WEEKEND",
                "label": "Fin de Semana (OTC)",
                "is_morning_real": False,
                "confidence_bonus": Decimal("0.0"),
                "recommended_target_pct": Decimal("3.0"),
                "description": "Mercado OTC algorítmico de fin de semana. Modo conservador y aprendizaje activo."
            }

        # Monday - Friday
        # Morning session: 07:00 - 12:00 (Peak interbank market overlap)
        if 7 <= hour < 12:
            return {
                "regime": "REAL_MORNING_PEAK",
                "label": "Mañana Mercado Real (Londres/NY) 🏦",
                "is_morning_real": True,
                "confidence_bonus": Decimal("0.10"),
                "recommended_target_pct": Decimal("5.0"),
                "description": "Horario bancario de máxima liquidez y volumen real. Mercado regulado y óptimo para meta del 5%."
            }
        elif 12 <= hour < 17:
            return {
                "regime": "REAL_AFTERNOON",
                "label": "Tarde Mercado Real 🇺🇸",
                "is_morning_real": False,
                "confidence_bonus": Decimal("0.05"),
                "recommended_target_pct": Decimal("4.0"),
                "description": "Sesión de tarde de Nueva York. Tendencias estables."
            }
        else:
            return {
                "regime": "NIGHT_OTC",
                "label": "Noche / Transición Asiática 🌙",
                "is_morning_real": False,
                "confidence_bonus": Decimal("0.0"),
                "recommended_target_pct": Decimal("3.0"),
                "description": "Sesión nocturna. Menor liquidez interbancaria. Meta prudente del 3%."
            }

    def get_target_pct(self) -> Decimal:
        """Returns target percentage depending on mode and market conditions."""
        if self.target_mode in ("3.5%", "3.5"):
            return Decimal("3.5")
        elif self.target_mode in ("3%", "3"):
            return Decimal("3.0")
        elif self.target_mode in ("4%", "4"):
            return Decimal("4.0")
        elif self.target_mode in ("5%", "5"):
            return Decimal("5.0")
        else:
            # AUTO mode: 5.0% in peak morning real market, 3.0% in OTC or night
            regime = self.get_market_regime()
            return regime["recommended_target_pct"]

    def record_trade_result(self, net_profit: Decimal, is_win: bool, current_equity: Decimal) -> Dict[str, Any]:
        """
        Updates session statistics after a trade closes and evaluates if target is met.
        """
        self.session_closed_trades += 1
        if is_win:
            self.session_wins += 1
        else:
            self.session_losses += 1

        self.session_net_profit += net_profit
        self.current_equity = current_equity

        profit_pct = Decimal("0.0")
        if self.session_starting_equity > Decimal("0"):
            profit_pct = (self.session_net_profit / self.session_starting_equity) * Decimal("100")

        target_pct = self.get_target_pct()
        target_amount = (self.session_starting_equity * target_pct) / Decimal("100")

        just_reached = False
        target_reason = ""

        # MODO MARATÓN DE APRENDIZAJE: Operar continuamente hasta superar $10,000 USD o caer a $0
        if self.target_mode in ("MARATON_10K", "MARATON", "10K", "APRENDIZAJE"):
            target_pct = Decimal("100.0")
            target_amount = Decimal("10000.00")
            if current_equity >= Decimal("10000.00") and not self.is_target_reached:
                self.is_target_reached = True
                self.target_reached_at = datetime.now()
                just_reached = True
                target_reason = "META_10K_ALCANZADA"
                logger.info(f"[SESSION MANAGER] 🏆 ¡META DE MARATÓN CUMPLIDA! Saldo superó $10,000 USD (${current_equity:,.2f})")
            elif current_equity <= Decimal("50.00") and not self.is_target_reached:
                self.is_target_reached = True
                self.target_reached_at = datetime.now()
                just_reached = True
                target_reason = "STOP_SALDO_CERO"
                logger.warning(f"[SESSION MANAGER] 🛑 MARATÓN DETENIDA: Saldo llegó al límite inferior (${current_equity:,.2f})")
        else:
            target_pct = self.get_target_pct()
            target_amount = (self.session_starting_equity * target_pct) / Decimal("100")
            max_session_loss_pct = Decimal("3.0")
            if profit_pct >= target_pct and not self.is_target_reached:
                self.is_target_reached = True
                self.target_reached_at = datetime.now()
                just_reached = True
                target_reason = "TARGET_PERCENT_REACHED"
                logger.info(
                    f"[SESSION MANAGER] 🎯 PROFIT TARGET REACHED! Profit: +${self.session_net_profit:,.2f} "
                    f"(+{profit_pct:.2f}%), Target was: {target_pct}%. Stopping bot to lock profits."
                )
            elif profit_pct <= -max_session_loss_pct and not self.is_target_reached:
                self.is_target_reached = True
                self.target_reached_at = datetime.now()
                just_reached = True
                target_reason = "STOP_LOSS_SESION"
                logger.warning(
                    f"[SESSION MANAGER] 🛡️ STOP LOSS DE SESIÓN ACTIVADO! Pérdida acumulada: ${self.session_net_profit:,.2f} "
                    f"({profit_pct:.2f}%). Deteniendo bot para proteger capital."
                )

        return {
            "session_profit": self.session_net_profit,
            "session_profit_pct": profit_pct,
            "target_pct": target_pct,
            "target_amount": target_amount,
            "is_target_reached": self.is_target_reached,
            "just_reached": just_reached,
            "target_reason": target_reason,
            "trades_count": self.session_closed_trades,
            "wins": self.session_wins,
            "losses": self.session_losses,
        }

    def check_hourly_cycle(self) -> Tuple[bool, str]:
        """
        Checks if the bot should be active or resting based on the hourly schedule.
        Returns (can_trade: bool, status_message: str).
        """
        if not self.hourly_cycle_enabled:
            return True, "Modo continuo 24/7 sin descansos por hora."

        elapsed_sec = time.time() - self.cycle_start_time
        active_sec = self.active_minutes * 60
        rest_sec = self.rest_minutes * 60

        if self.cycle_state == "ACTIVE":
            if elapsed_sec >= active_sec:
                # Switch to RESTING
                self.cycle_state = "RESTING"
                self.cycle_start_time = time.time()
                logger.info(f"[SESSION MANAGER] ⏱️ 1-hour active block completed. Entering RESTING cooldown ({self.rest_minutes} min).")
                return False, f"Descanso programado iniciado. Reposo de {self.rest_minutes} minutos para enfriar el mercado."
            else:
                remaining_min = int((active_sec - elapsed_sec) / 60)
                return True, f"Bloque activo: quedan {remaining_min} min de operativa."

        elif self.cycle_state == "RESTING":
            if elapsed_sec >= rest_sec:
                # Switch to ACTIVE
                self.cycle_state = "ACTIVE"
                self.cycle_start_time = time.time()
                logger.info("[SESSION MANAGER] ⏱️ Rest cooldown finished. Resuming new 1-hour active block.")
                return True, "Descanso completado. Reanudando bloque activo de operaciones."
            else:
                remaining_rest = int((rest_sec - elapsed_sec) / 60)
                return False, f"En reposo de seguridad: faltan {remaining_rest} min para el siguiente bloque activo."

        return True, "OK"

    def get_progress_data(self) -> Dict[str, Any]:
        """Generates detailed progress indicators for Telegram and Dashboard."""
        profit_pct = Decimal("0.0")
        if self.session_starting_equity > Decimal("0"):
            profit_pct = (self.session_net_profit / self.session_starting_equity) * Decimal("100")

        if self.target_mode in ("MARATON_10K", "MARATON", "10K", "APRENDIZAJE"):
            target_pct = Decimal("100.0")
            target_amount = Decimal("10000.00")
            remaining_profit = max(Decimal("0.0"), Decimal("10000.00") - self.current_equity)
            completion_ratio = float(self.current_equity / Decimal("10000.00")) if self.current_equity > Decimal("0") else 0.0
            clamped_ratio = max(0.0, min(1.0, completion_ratio))
            filled_segments = int(round(clamped_ratio * 10))
            bar = "🟩" * filled_segments + "⬜" * (10 - filled_segments)
        else:
            target_pct = self.get_target_pct()
            target_amount = (self.session_starting_equity * target_pct) / Decimal("100")
            remaining_profit = max(Decimal("0.0"), target_amount - self.session_net_profit)

            # Visual progress bar (10 segments)
            completion_ratio = float(profit_pct / target_pct) if target_pct > Decimal("0") else 0.0
            clamped_ratio = max(0.0, min(1.0, completion_ratio))
            filled_segments = int(round(clamped_ratio * 10))
            bar = "🟩" * filled_segments + "⬜" * (10 - filled_segments)

        # Cycle time remaining
        elapsed_sec = time.time() - self.cycle_start_time
        if self.cycle_state == "ACTIVE":
            total_sec = self.active_minutes * 60
        else:
            total_sec = self.rest_minutes * 60
        rem_min = max(0, int((total_sec - elapsed_sec) / 60))

        regime = self.get_market_regime()

        return {
            "starting_equity": self.session_starting_equity,
            "current_equity": self.current_equity,
            "net_profit": self.session_net_profit,
            "profit_pct": profit_pct,
            "target_pct": target_pct,
            "target_amount": target_amount,
            "remaining_profit": remaining_profit,
            "progress_bar": bar,
            "completion_pct": round(clamped_ratio * 100, 1),
            "is_target_reached": self.is_target_reached,
            "target_mode": self.target_mode,
            "cycle_state": self.cycle_state,
            "cycle_remaining_min": rem_min,
            "hourly_cycle_enabled": self.hourly_cycle_enabled,
            "market_regime": regime,
            "closed_trades": self.session_closed_trades,
            "wins": self.session_wins,
            "losses": self.session_losses,
            "win_rate": round((self.session_wins / self.session_closed_trades * 100), 1) if self.session_closed_trades > 0 else 0.0,
        }


