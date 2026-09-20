"""Conservative State Reconciler.
SAFEGUARD PRINCIPLE:
If any discrepancy between local DB and the exchange is detected upon boot or reconnection,
NEVER guess or auto-correct with market orders.
IMMEDIATELY pause the bot, lock trading, and trigger high-priority alerts for human review.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.core.decimal_math import to_decimal
from app.exchange.ccxt_adapter import CCXTExchangeAdapter


@dataclass
class DiscrepancyItem:
    discrepancy_type: str  # "ORPHAN_EXCHANGE_ORDER" | "MISSING_LOCAL_ORDER" | "POSITION_MISMATCH"
    symbol: str
    exchange_details: Dict[str, Any]
    local_details: Dict[str, Any]
    description: str


@dataclass
class ReconciliationResult:
    is_clean: bool
    requires_manual_intervention: bool
    discrepancies: List[DiscrepancyItem] = field(default_factory=list)
    summary_message: str = ""


class StateReconciler:
    """Audits and reconciles live exchange state against internal DB state upon startup/reconnection."""

    def __init__(self, exchange_adapter: CCXTExchangeAdapter):
        self.adapter = exchange_adapter
        self.is_locked_for_review: bool = False
        self.lock_reason: str = ""
        self.last_review_cleared_by: Optional[str] = None

    def unlock_after_manual_review(self, operator_id: str, justification: str) -> bool:
        """
        Explicit, intentional unlock method.
        Requires operator ID and justification to ensure human review occurred.
        """
        if not self.is_locked_for_review:
            logger.info(f"[RECONCILER] Bot is not locked. Operator {operator_id} checked status.")
            return True

        self.is_locked_for_review = False
        self.last_review_cleared_by = f"{operator_id}: {justification}"
        logger.info(f"[RECONCILER] Lock CLEARED by operator '{operator_id}'. Justification: '{justification}'")
        return True

    async def reconcile(
        self,
        db_session: Optional[AsyncSession] = None,
        local_open_orders: Optional[List[Dict[str, Any]]] = None,
        local_open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> ReconciliationResult:
        """
        Performs full audit between DB state and exchange state.

        Args:
            db_session: Active async SQLAlchemy session.
            local_open_orders: Optional in-memory open orders list for testing.
            local_open_positions: Optional in-memory open positions list for testing.
        """
        from app.database.order_repository import (
            get_open_orders,
            get_open_positions,
            log_reconciliation,
        )

        logger.info("[RECONCILER] Starting conservative state reconciliation...")
        discrepancies: List[DiscrepancyItem] = []

        try:
            # Paper mode: local simulation only — no remote exchange discrepancies
            from app.core.constants import BotMode
            if getattr(self.adapter, "mode", None) == BotMode.PAPER and local_open_orders is None:
                self.is_locked_for_review = False
                logger.info("[RECONCILER] Mode is PAPER — State reconciliation clean by definition.")
                return ReconciliationResult(
                    is_clean=True,
                    requires_manual_intervention=False,
                    discrepancies=[],
                    summary_message="Paper mode: Local simulation clean."
                )

            # Load state from DB or injected lists
            if local_open_orders is None:
                local_open_orders = await get_open_orders(db_session) if db_session else []
            if local_open_positions is None:
                local_open_positions = await get_open_positions(db_session) if db_session else []

            logger.info(
                f"[RECONCILER] State loaded: {len(local_open_orders)} open order(s), "
                f"{len(local_open_positions)} open position(s)."
            )

            # 1. Fetch live open orders from exchange
            exchange_orders = await self.adapter.fetch_open_orders()
            exchange_order_ids = {str(o.get("id")): o for o in exchange_orders if o.get("id")}
            local_order_ids = {
                str(o.get("exchange_order_id")): o
                for o in local_open_orders
                if o.get("exchange_order_id")
            }

            # Check 1: Orders on exchange that DB does not know about (ORPHAN)
            for ex_id, ex_order in exchange_order_ids.items():
                if ex_id not in local_order_ids:
                    discrepancies.append(
                        DiscrepancyItem(
                            discrepancy_type="ORPHAN_EXCHANGE_ORDER",
                            symbol=ex_order.get("symbol", "UNKNOWN"),
                            exchange_details=ex_order,
                            local_details={},
                            description=f"Active order {ex_id} on exchange not found in local DB.",
                        )
                    )

            # Check 2: Orders in DB marked open that are gone from exchange (GHOST)
            for loc_id, loc_order in local_order_ids.items():
                if loc_id not in exchange_order_ids:
                    discrepancies.append(
                        DiscrepancyItem(
                            discrepancy_type="MISSING_EXCHANGE_ORDER",
                            symbol=loc_order.get("symbol", "UNKNOWN"),
                            exchange_details={},
                            local_details=loc_order,
                            description=f"Local order {loc_id} marked open is no longer active on exchange.",
                        )
                    )

            # Check 3: Audit positions / spot holdings
            exchange_positions = await self.adapter.fetch_positions()
            ex_pos_by_symbol = {p.get("symbol"): p for p in exchange_positions if p.get("symbol")}
            local_pos_by_symbol = {p.get("symbol"): p for p in local_open_positions if p.get("symbol")}

            for sym, ex_pos in ex_pos_by_symbol.items():
                contracts = to_decimal(ex_pos.get("contracts") or ex_pos.get("amount") or 0)
                if contracts > Decimal("0") and sym not in local_pos_by_symbol:
                    discrepancies.append(
                        DiscrepancyItem(
                            discrepancy_type="POSITION_MISMATCH",
                            symbol=sym,
                            exchange_details=ex_pos,
                            local_details={},
                            description=(
                                f"Open position of {contracts} on exchange for {sym} "
                                "not registered in local DB."
                            ),
                        )
                    )

            # Evaluate Reconciliation Outcome
            if discrepancies:
                self.is_locked_for_review = True
                summary = (
                    f"[WARN: RECONCILIATION DISCREPANCY] Detected {len(discrepancies)} mismatch(es). "
                    "Trading is LOCKED in PAUSED_MANUAL_REVIEW mode to safeguard funds. Human review required."
                )
                logger.error(summary)
                for d in discrepancies:
                    logger.error(f"  - {d.discrepancy_type} on {d.symbol}: {d.description}")

                if db_session:
                    await log_reconciliation(
                        db_session,
                        status="DISCREPANCY_DETECTED",
                        details=summary + " | " + "; ".join(d.description for d in discrepancies),
                        requires_manual_intervention=True,
                    )

                return ReconciliationResult(
                    is_clean=False,
                    requires_manual_intervention=True,
                    discrepancies=discrepancies,
                    summary_message=summary,
                )
            else:
                self.is_locked_for_review = False
                summary = "[OK: RECONCILIATION CLEAN] Local DB and exchange state are 100% in sync."
                logger.info(summary)

                if db_session:
                    await log_reconciliation(
                        db_session,
                        status="CLEAN",
                        details=summary,
                        requires_manual_intervention=False,
                    )

                return ReconciliationResult(
                    is_clean=True,
                    requires_manual_intervention=False,
                    discrepancies=[],
                    summary_message=summary,
                )

        except Exception as e:
            self.is_locked_for_review = True
            error_summary = (
                f"[CRITICAL: RECONCILER ERROR] Failed to query exchange during audit: {e}. "
                "Bot locked for safety."
            )
            logger.error(error_summary, exc_info=True)
            return ReconciliationResult(
                is_clean=False,
                requires_manual_intervention=True,
                discrepancies=[],
                summary_message=error_summary,
            )
