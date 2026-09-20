"""Database Models for Orders, Positions, Trades, and Audit Trail."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Boolean,
    Text,
    Enum as SAEnum
)
from sqlalchemy.orm import declarative_base
from app.core.constants import OrderSide, OrderType, OrderStatus, BotMode

Base = declarative_base()


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_order_id = Column(String(64), unique=True, index=True, nullable=False)
    exchange_order_id = Column(String(64), index=True, nullable=True)
    symbol = Column(String(20), index=True, nullable=False)
    exchange_id = Column(String(20), nullable=False)
    mode = Column(SAEnum(BotMode), nullable=False)
    side = Column(SAEnum(OrderSide), nullable=False)
    order_type = Column(SAEnum(OrderType), nullable=False)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.CREATED, nullable=False)

    # Decimal Fields stored with high precision
    price = Column(Numeric( precision=24, scale=8), nullable=True)
    stop_price = Column(Numeric(precision=24, scale=8), nullable=True)
    amount = Column(Numeric(precision=24, scale=8), nullable=False)
    filled_amount = Column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)
    remaining_amount = Column(Numeric(precision=24, scale=8), nullable=False)
    avg_fill_price = Column(Numeric(precision=24, scale=8), nullable=True)
    fee_paid = Column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)
    fee_currency = Column(String(10), nullable=True)

    strategy_name = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PositionModel(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    exchange_id = Column(String(20), nullable=False)
    mode = Column(SAEnum(BotMode), nullable=False)
    is_open = Column(Boolean, default=True, nullable=False)
    
    amount = Column(Numeric(precision=24, scale=8), nullable=False)
    entry_price = Column(Numeric(precision=24, scale=8), nullable=False)
    current_price = Column(Numeric(precision=24, scale=8), nullable=True)
    stop_loss = Column(Numeric(precision=24, scale=8), nullable=True)
    take_profit = Column(Numeric(precision=24, scale=8), nullable=True)
    realized_pnl = Column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)
    unrealized_pnl = Column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)

    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class ReconciliationLogModel(Base):
    __tablename__ = "reconciliation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(30), nullable=False)  # "CLEAN" | "DISCREPANCY_DETECTED"
    details = Column(Text, nullable=False)
    requires_manual_intervention = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
