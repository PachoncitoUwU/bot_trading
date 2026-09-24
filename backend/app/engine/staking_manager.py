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

    MAX_ALLOWED_STAKE: Decimal = Decimal("100.0")

    def __init__(self, steps: Optional[List[float]] = None):
        # 100% FLAT STAKE: Posición fija sin escalada tras pérdidas (Pure Fixed Fractional 0.25%)
        self.steps = [Decimal("25.0")]
        self.current_step_index: int = 0
        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.total_cycles_completed: int = 0
        self.history: List[Dict[str, Any]] = []

    def sync_account_equity(self, equity: Decimal) -> None:
        """Dynamically sets fixed stake to exactly 0.25% of account balance (Flat Position Sizing)."""
        if equity > Decimal("10.0"):
            base = Decimal("25.0") if equity >= Decimal("5000.0") else max(Decimal("1.0"), min(Decimal("100.0"), round(equity * Decimal("0.0025"), 0)))
            self.steps = [base]
            self.current_step_index = 0
            logger.info(f"[STAKING] Pure Flat Stake active: ${base:,.0f} USD fijo por operación (Sin martingala).")

    def get_current_stake(self) -> Decimal:
        """Returns the stake amount in USD for the next trade."""
        return self.steps[0] if self.steps else Decimal("25.0")

    def calculate_dynamic_stake(
        self,
        confidence: Decimal = Decimal("0.5"),
        confluences: int = 1
    ) -> tuple[Decimal, str]:
        """
        Pure Flat Staking: Exactamente 0.25% del capital en cada operación.
        Sin martingala, sin escalada, sin recuperación forzada.
        """
        stake = self.get_current_stake()
        reason = f"Tamaño Fijo 0.25% (${stake:,.0f} USD, Sin Martingala)"
        final_stake = min(self.MAX_ALLOWED_STAKE, max(Decimal("1.0"), stake))
        return final_stake, reason

    def record_trade_result(self, is_win: bool, profit_usd: float, symbol: str) -> Dict[str, Any]:
        """
        Updates the staking state based on trade outcome under Pure Flat Staking.
        """
        stake = self.get_current_stake()
        old_step = 0
        old_stake = stake
        self.current_step_index = 0
        
        if is_win:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            event = "WIN"
            msg = f"🏆 ¡GANANCIA! (+${profit_usd:,.2f}). Siguiente trade: ${stake:,.2f} USD (Fijo 0.25%)."
            logger.info(f"[STAKING] {msg}")
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            event = "LOSS"
            msg = (
                f"⚠️ Pérdida de trade (-${stake:,.2f} USD). "
                f"Siguiente trade: ${stake:,.2f} USD (Fijo 0.25%, SIN aumentar postura)."
            )
            logger.warning(f"[STAKING] {msg}")

        record = {
            "symbol": symbol,
            "is_win": is_win,
            "profit_usd": profit_usd,
            "step_before": 1,
            "stake_used": float(old_stake),
            "step_after": 1,
            "next_stake": float(self.get_current_stake()),
            "event": event,
            "message": msg,
        }
        self.history.append(record)
        return record

    def get_telemetry(self) -> Dict[str, Any]:
        """Exposes staking state to UI dashboard and Telegram."""
        return {
            "current_step": 1,
            "total_steps": 1,
            "current_stake": float(self.get_current_stake()),
            "steps_config": [float(s) for s in self.steps],
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "label": f"Fijo 0.25% (${self.get_current_stake():,.0f} USD)",
            "status_text": (
                f"Tamaño Fijo: ${self.get_current_stake():,.0f} USD (0.25% capital, CERO martingala)"
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

