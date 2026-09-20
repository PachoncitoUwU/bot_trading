"""Interactive Signal Manager with TTL (Time-To-Live) and Price Drift Expiration."""
import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, Optional, Tuple
from app.core.config import settings
from app.core.constants import SignalType
from app.core.logger import logger
from app.strategies.base_strategy import StrategySignal


@dataclass
class PendingInteractiveSignal:
    signal_id: str
    signal: StrategySignal
    created_at: float
    ttl_seconds: int
    entry_price: Decimal
    max_price_drift_pct: Decimal = Decimal("0.3")  # 0.3% max price slippage while waiting
    is_resolved: bool = False
    resolution_status: str = "PENDING"  # "APPROVED" | "REJECTED" | "EXPIRED_TTL" | "EXPIRED_PRICE_DRIFT"


class InteractiveSignalManager:
    """Manages Telegram signal confirmation prompts with automatic TTL and price drift expiration."""

    def __init__(self, default_ttl_seconds: int = 45):
        self.default_ttl = default_ttl_seconds
        self.pending_signals: Dict[str, PendingInteractiveSignal] = {}

    def create_pending_signal(self, signal: StrategySignal, signal_id: Optional[str] = None) -> PendingInteractiveSignal:
        sig_id = signal_id or f"SIG_{int(time.time()*1000)}"
        pending = PendingInteractiveSignal(
            signal_id=sig_id,
            signal=signal,
            created_at=time.time(),
            ttl_seconds=self.default_ttl,
            entry_price=signal.price
        )
        self.pending_signals[sig_id] = pending
        logger.info(f"[TELEGRAM] Interactive signal {sig_id} created for {signal.symbol}. Waiting for approval (TTL: {self.default_ttl}s).")
        return pending

    def check_expiration(self, signal_id: str, current_market_price: Optional[Decimal] = None) -> Tuple[bool, str]:
        """
        Checks if a pending signal has expired due to TTL timeout or price drift.
        Returns: (is_expired, reason)
        """
        pending = self.pending_signals.get(signal_id)
        if not pending or pending.is_resolved:
            return True, "Signal already resolved or not found."

        elapsed = time.time() - pending.created_at
        if elapsed > pending.ttl_seconds:
            pending.is_resolved = True
            pending.resolution_status = "EXPIRED_TTL"
            logger.warning(f"[TELEGRAM] Signal {signal_id} EXPIRED: Exceeded {pending.ttl_seconds}s timeout without response.")
            return True, f"Signal expired: Timeout ({pending.ttl_seconds}s exceeded)."

        if current_market_price is not None:
            price_drift_pct = abs((current_market_price - pending.entry_price) / pending.entry_price) * Decimal("100")
            if price_drift_pct > pending.max_price_drift_pct:
                pending.is_resolved = True
                pending.resolution_status = "EXPIRED_PRICE_DRIFT"
                logger.warning(f"[TELEGRAM] Signal {signal_id} EXPIRED: Price moved by {price_drift_pct:.2f}% (Limit: {pending.max_price_drift_pct}%).")
                return True, f"Signal expired: Price drifted by {price_drift_pct:.2f}%."

        return False, "Signal active."

    def resolve_signal(self, signal_id: str, approve: bool, operator_id: str) -> Tuple[bool, Optional[StrategySignal], str]:
        """
        Approves or rejects a pending signal from Telegram button callback.
        """
        is_expired, expire_reason = self.check_expiration(signal_id)
        pending = self.pending_signals.get(signal_id)

        if not pending:
            return False, None, "Signal not found."

        if pending.is_resolved and pending.resolution_status.startswith("EXPIRED"):
            return False, None, f"Cannot execute: {expire_reason}"

        pending.is_resolved = True
        if approve:
            pending.resolution_status = "APPROVED"
            logger.info(f"[TELEGRAM] Signal {signal_id} APPROVED by {operator_id}.")
            return True, pending.signal, f"Signal approved by {operator_id}. Executing order."
        else:
            pending.resolution_status = "REJECTED"
            logger.info(f"[TELEGRAM] Signal {signal_id} REJECTED by {operator_id}.")
            return True, None, f"Signal rejected by {operator_id}."
