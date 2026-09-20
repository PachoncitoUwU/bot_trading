"""Institutional Staking & Money Management for Binary Options / IQ Option.

Implements Controlled 3-Step Martingale Recovery:
- Step 1: Base Stake (e.g. $50)
- On Loss -> Step 2: 2x Stake (e.g. $100)
- On Loss -> Step 3: 4x Stake (e.g. $200)
- On Loss at Step 3 -> HARD RESET to Step 1 ($50) to protect account capital
- On WIN at ANY Step -> Immediate RESET to Step 1 ($50)
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.decimal_math import to_decimal
from app.core.logger import logger


class StakingManager:
    """Manages dynamic position sizing, conviction-based scaling, and recovery sequences."""

    MAX_ALLOWED_STAKE: Decimal = Decimal("200.0")

    def __init__(self, steps: Optional[List[float]] = None):
        self.steps: List[Decimal] = [
            to_decimal(str(s)) for s in (steps or settings.IQOPTION_MARTINGALE_STEPS or [50.0, 100.0, 200.0])
        ]
        if not self.steps:
            self.steps = [Decimal("50.0"), Decimal("100.0"), Decimal("200.0")]
            
        self.current_step_index: int = 0
        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.total_martingale_cycles_completed: int = 0
        self.history: List[Dict[str, Any]] = []

    def get_current_stake(self) -> Decimal:
        """Returns the stake amount in USD for the next trade, bounded by max $200."""
        if 0 <= self.current_step_index < len(self.steps):
            raw_stake = self.steps[self.current_step_index]
        else:
            raw_stake = self.steps[0]
        return min(self.MAX_ALLOWED_STAKE, raw_stake)

    def calculate_dynamic_stake(
        self,
        confidence: Decimal = Decimal("0.5"),
        confluences: int = 1
    ) -> tuple[Decimal, str]:
        """
        Calculates stake size based on exact 3-step recovery sequence ($50 -> $100 -> $200):
        - Paso 1 (Base): $50 USD
        - Paso 2 (Recuperación tras 1 pérdida): $100 USD
        - Paso 3 (Recuperación tras 2 pérdidas): $200 USD (Hard Cap de Seguridad con Ultra-Filtro)
        - Tras ganar en cualquier paso: Reseteo inmediato al Paso 1 ($50 USD).
        - Si se pierde en el Paso 3: Freno de seguridad y reseteo al Paso 1 ($50 USD) para no arriesgar la cuenta.
        """
        if self.current_step_index > 0:
            stake = self.get_current_stake()
            reason = f"Recuperación Inteligente (Paso {self.current_step_index + 1}: ${stake:,.0f} USD)"
        else:
            stake = self.steps[0] if self.steps else Decimal("50.0")
            reason = f"Stake Base Estándar ${stake:,.0f} USD"

        final_stake = min(self.MAX_ALLOWED_STAKE, max(Decimal("1.0"), stake))
        return final_stake, reason

    def record_trade_result(self, is_win: bool, profit_usd: float, symbol: str) -> Dict[str, Any]:
        """
        Updates the staking state based on trade outcome.
        Returns outcome metadata.
        """
        old_step = self.current_step_index
        old_stake = self.steps[old_step]
        
        if is_win:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.current_step_index = 0
            event = "WIN_RESET"
            msg = f"🏆 ¡GANANCIA! (+${profit_usd:,.2f}). Reiniciando al Paso 1 (${self.steps[0]:,.2f} USD)."
            logger.info(f"[STAKING] {msg}")
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            if self.current_step_index + 1 < len(self.steps):
                self.current_step_index += 1
                event = "LOSS_ADVANCE"
                next_stake = self.steps[self.current_step_index]
                msg = (
                    f"⚠️ Pérdida en Paso {old_step + 1} (${old_stake:,.2f}). "
                    f"Avanzando a Paso {self.current_step_index + 1} (${next_stake:,.2f} USD) para recuperar."
                )
                logger.warning(f"[STAKING] {msg}")
            else:
                self.current_step_index = 0
                self.total_martingale_cycles_completed += 1
                event = "LOSS_RESET_PROTECTION"
                msg = (
                    f"🛑 Pérdida en Paso {len(self.steps)} (${old_stake:,.2f}). "
                    f"Freno de seguridad activado: Reiniciando al Paso 1 (${self.steps[0]:,.2f} USD) para proteger tu capital."
                )
                logger.warning(f"[STAKING] {msg}")

        record = {
            "symbol": symbol,
            "is_win": is_win,
            "profit_usd": profit_usd,
            "step_before": old_step + 1,
            "stake_used": float(old_stake),
            "step_after": self.current_step_index + 1,
            "next_stake": float(self.get_current_stake()),
            "event": event,
            "message": msg,
        }
        self.history.append(record)
        return record

    def get_telemetry(self) -> Dict[str, Any]:
        """Exposes staking state to UI dashboard and Telegram."""
        return {
            "current_step": self.current_step_index + 1,
            "total_steps": len(self.steps),
            "current_stake": float(self.get_current_stake()),
            "steps_config": [float(s) for s in self.steps],
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "label": f"Paso {self.current_step_index + 1}/{len(self.steps)} (${self.get_current_stake():,.0f} USD)",
            "status_text": (
                f"Siguiente operación: ${self.get_current_stake():,.0f} USD "
                f"(Paso {self.current_step_index + 1} de {len(self.steps)})"
            ),
        }

    def set_steps(self, steps: List[float]) -> List[float]:
        """Updates martingale progression steps dynamically."""
        valid = [to_decimal(str(max(1.0, float(s)))) for s in steps if float(s) > 0]
        if valid:
            self.steps = valid
            self.current_step_index = 0
            logger.info(f"[STAKING] Steps updated to: {[float(s) for s in self.steps]}")
        return [float(s) for s in self.steps]

    def set_base_stake(self, base_stake: float) -> List[float]:
        """Sets 1x, 2x, 4x progression from a given base stake (e.g. 1.0 -> [1.0, 2.0, 4.0])."""
        base = max(1.0, float(base_stake))
        return self.set_steps([base, base * 2.0, base * 4.0])

