"""Async SQLAlchemy engine, session factory, and database initialization."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.config import settings
from app.core.logger import logger

# Create the async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,          # Set True to debug SQL queries
    future=True,
    pool_pre_ping=True,  # Verify connections before use
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    """
    Creates all tables defined in models.py.
    Safe to call on every startup — only creates tables that do not exist.
    """
    from app.database.models import Base  # local import to avoid circular deps

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("[DB] Database initialized. All tables verified/created.")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for a database session.
    Commits on success, rolls back on any exception, always closes.

    Usage:
        async with get_db_session() as session:
            result = await order_repo.get_open_orders(session)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Disposes the engine connection pool on shutdown."""
    await engine.dispose()
    logger.info("[DB] Database engine disposed.")
