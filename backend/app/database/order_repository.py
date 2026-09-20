"""Async repository for Order and Position persistence.

All DB writes go through this module — no SQLAlchemy calls scattered across the app.
The StateReconciler reads from here; BotRunner writes here.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BotMode, OrderSide, OrderStatus, OrderType
from app.core.logger import logger
from app.database.models import OrderModel, PositionModel, ReconciliationLogModel


# ─────────────────────────────────────────────
# Order Operations
# ─────────────────────────────────────────────

def generate_client_order_id(prefix: str = "BOT") -> str:
    """Generates a unique client order ID for idempotent order submission."""
    return f"{prefix}_{uuid.uuid4().hex[:16].upper()}"


async def create_order_record(
    session: AsyncSession,
    *,
    client_order_id: str,
    symbol: str,
    exchange_id: str,
    mode: BotMode,
    side: OrderSide,
    order_type: OrderType,
    amount: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    strategy_name: Optional[str] = None,
) -> OrderModel:
    """Inserts a new order record with status=CREATED before sending to exchange."""
    order = OrderModel(
        client_order_id=client_order_id,
        exchange_order_id=None,  # Populated after exchange confirms
        symbol=symbol,
        exchange_id=exchange_id,
        mode=mode,
        side=side,
        order_type=order_type,
        status=OrderStatus.CREATED,
        price=price,
        stop_price=stop_price,
        amount=amount,
        filled_amount=Decimal("0"),
        remaining_amount=amount,
        strategy_name=strategy_name,
    )
    session.add(order)
    await session.flush()  # Get the auto-generated id without committing yet
    logger.info(f"[DB] Order created: {client_order_id} | {side.value} {amount} {symbol}")
    return order


async def update_order_from_exchange(
    session: AsyncSession,
    *,
    client_order_id: str,
    exchange_order_id: str,
    status: OrderStatus,
    filled_amount: Optional[Decimal] = None,
    avg_fill_price: Optional[Decimal] = None,
    fee_paid: Optional[Decimal] = None,
    fee_currency: Optional[str] = None,
) -> bool:
    """Updates an order record once the exchange confirms it (fill, cancel, etc.)."""
    values: Dict[str, Any] = {
        "exchange_order_id": exchange_order_id,
        "status": status,
        "updated_at": datetime.utcnow(),
    }
    if filled_amount is not None:
        values["filled_amount"] = filled_amount
    if avg_fill_price is not None:
        values["avg_fill_price"] = avg_fill_price
    if fee_paid is not None:
        values["fee_paid"] = fee_paid
    if fee_currency is not None:
        values["fee_currency"] = fee_currency

    result = await session.execute(
        update(OrderModel)
        .where(OrderModel.client_order_id == client_order_id)
        .values(**values)
    )
    updated = result.rowcount > 0
    if updated:
        logger.info(
            f"[DB] Order updated: {client_order_id} -> status={status.value}, "
            f"exchange_id={exchange_order_id}, filled={filled_amount}"
        )
    else:
        logger.warning(f"[DB] update_order_from_exchange: client_order_id '{client_order_id}' not found.")
    return updated


async def get_open_orders(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Returns all locally tracked orders that are still considered open (CREATED or PARTIAL).
    Used by StateReconciler to compare against exchange state.
    """
    result = await session.execute(
        select(OrderModel).where(
            OrderModel.status.in_([OrderStatus.CREATED, OrderStatus.PARTIALLY_FILLED])
        )
    )
    orders = result.scalars().all()
    return [
        {
            "client_order_id": o.client_order_id,
            "exchange_order_id": o.exchange_order_id,
            "symbol": o.symbol,
            "side": o.side.value,
            "amount": str(o.amount),
            "filled_amount": str(o.filled_amount),
            "status": o.status.value,
        }
        for o in orders
    ]


# ─────────────────────────────────────────────
# Position Operations
# ─────────────────────────────────────────────

async def upsert_position(
    session: AsyncSession,
    *,
    symbol: str,
    exchange_id: str,
    mode: BotMode,
    amount: Decimal,
    entry_price: Decimal,
    stop_loss: Optional[Decimal] = None,
    take_profit: Optional[Decimal] = None,
) -> PositionModel:
    """Creates or updates an open position record."""
    result = await session.execute(
        select(PositionModel).where(
            PositionModel.symbol == symbol,
            PositionModel.is_open == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.amount = amount
        existing.entry_price = entry_price
        existing.stop_loss = stop_loss
        existing.take_profit = take_profit
        logger.info(f"[DB] Position updated: {symbol} | {amount} @ {entry_price}")
        return existing
    else:
        pos = PositionModel(
            symbol=symbol,
            exchange_id=exchange_id,
            mode=mode,
            is_open=True,
            amount=amount,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
        )
        session.add(pos)
        await session.flush()
        logger.info(f"[DB] Position created: {symbol} | {amount} @ {entry_price}")
        return pos


async def close_position_record(
    session: AsyncSession,
    symbol: str,
    realized_pnl: Decimal,
) -> bool:
    """Marks a position as closed with realized PnL."""
    result = await session.execute(
        update(PositionModel)
        .where(PositionModel.symbol == symbol, PositionModel.is_open == True)  # noqa: E712
        .values(
            is_open=False,
            closed_at=datetime.utcnow(),
            realized_pnl=realized_pnl,
        )
    )
    return result.rowcount > 0


async def get_open_positions(session: AsyncSession) -> List[Dict[str, Any]]:
    """Returns all locally tracked open positions for reconciliation."""
    result = await session.execute(
        select(PositionModel).where(PositionModel.is_open == True)  # noqa: E712
    )
    positions = result.scalars().all()
    return [
        {
            "symbol": p.symbol,
            "amount": str(p.amount),
            "entry_price": str(p.entry_price),
            "stop_loss": str(p.stop_loss) if p.stop_loss else None,
            "take_profit": str(p.take_profit) if p.take_profit else None,
        }
        for p in positions
    ]


# ─────────────────────────────────────────────
# Reconciliation Log
# ─────────────────────────────────────────────

async def log_reconciliation(
    session: AsyncSession,
    *,
    status: str,
    details: str,
    requires_manual_intervention: bool,
) -> None:
    """Persists a reconciliation audit log entry."""
    entry = ReconciliationLogModel(
        status=status,
        details=details,
        requires_manual_intervention=requires_manual_intervention,
    )
    session.add(entry)
    await session.flush()
    logger.info(f"[DB] Reconciliation log written: {status}")
