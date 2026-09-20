import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import ccxt.async_support as ccxt_async
except ImportError:
    ccxt_async = None

from app.core.config import settings
from app.core.constants import BotMode, OrderSide, OrderType, OrderStatus
from app.core.decimal_math import to_decimal
from app.core.logger import logger
from app.core.rate_limiter import exchange_rate_limiter
from app.core.time_sync import time_sync_manager
from app.exchange.symbol_rules import symbol_rules_cache, SymbolRules


class CCXTExchangeAdapter:
    """Unified asynchronous exchange adapter with rate-limiting and precision safeguards."""

    def __init__(self, exchange_id: Optional[str] = None, mode: Optional[BotMode] = None):
        self.exchange_id = exchange_id or settings.EXCHANGE_ID
        self.mode = mode or settings.BOT_MODE
        self.client: Any = None
        self.is_initialized = False

    async def initialize(self) -> None:
        """Initializes CCXT client with appropriate mode and fetches market rules."""
        if self.is_initialized and self.client:
            return

        exchange_class = getattr(ccxt_async, self.exchange_id, None)
        if not exchange_class:
            raise ValueError(f"Exchange '{self.exchange_id}' is not supported by CCXT.")

        config = {
            "enableRateLimit": True,
            "timeout": 20000,
            "options": {
                "defaultType": "spot",
                "warnOnFetchOpenOrdersWithoutSymbol": False,
                "fetchOpenOrders": {"warnWithoutSymbol": False}
            }
        }

        if self.mode in [BotMode.TESTNET, BotMode.LIVE]:
            if settings.EXCHANGE_API_KEY and settings.EXCHANGE_API_SECRET:
                config["apiKey"] = settings.EXCHANGE_API_KEY
                config["secret"] = settings.EXCHANGE_API_SECRET
            if settings.EXCHANGE_PASSWORD:
                config["password"] = settings.EXCHANGE_PASSWORD

        self.client = exchange_class(config)

        # Set sandbox / testnet mode if required
        if self.mode == BotMode.TESTNET or (settings.USE_TESTNET and self.mode != BotMode.LIVE):
            if hasattr(self.client, "set_sandbox_mode"):
                self.client.set_sandbox_mode(True)
                logger.info(f"[{self.exchange_id.upper()}] Sandbox / Testnet mode ENABLED.")

        # Load markets and sync server time
        try:
            await exchange_rate_limiter.acquire(weight=2.0)
            markets = await self.client.load_markets()
            for symbol, market_data in markets.items():
                symbol_rules_cache.parse_and_store_from_ccxt(market_data)

            # Sync exchange server time
            if hasattr(self.client, "fetch_time"):
                server_time = await self.client.fetch_time()
                is_healthy, drift_ms = time_sync_manager.sync_with_server_time(server_time)
                logger.info(f"[{self.exchange_id.upper()}] Time synced. Server Drift: {drift_ms}ms (Healthy: {is_healthy})")

            self.is_initialized = True
            logger.info(f"[{self.exchange_id.upper()}] Adapter successfully initialized in {self.mode.value} mode.")
        except Exception as e:
            logger.error(f"[{self.exchange_id.upper()}] Failed to load markets: {e}")
            if self.mode != BotMode.PAPER:
                raise

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List[Any]]:
        """Fetches OHLCV candlestick data."""
        await exchange_rate_limiter.acquire(weight=1.0)
        return await self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        """Fetches current last price for symbol as Decimal."""
        await exchange_rate_limiter.acquire(weight=1.0)
        ticker = await self.client.fetch_ticker(symbol)
        return to_decimal(ticker.get("last") or ticker.get("close", 0))

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """Fetches free and total balances in Decimal."""
        if self.mode == BotMode.PAPER:
            # Mock initial balance for Paper trading
            return {"USDT": Decimal("10000.00"), "BTC": Decimal("0.0"), "ETH": Decimal("0.0")}

        await exchange_rate_limiter.acquire(weight=2.0)
        raw_balance = await self.client.fetch_balance()
        balances = {}
        for currency, data in raw_balance.get("free", {}).items():
            if data and float(data) > 0:
                balances[currency] = to_decimal(data)
        return balances

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches open orders from exchange safely per symbol."""
        if self.mode == BotMode.PAPER:
            return []
        await exchange_rate_limiter.acquire(weight=2.0)
        if symbol:
            try:
                return await self.client.fetch_open_orders(symbol=symbol)
            except Exception as e:
                logger.warning(f"[CCXT] fetch_open_orders({symbol}) warning: {e}")
                return []

        all_orders = []
        for s in settings.TRADING_SYMBOLS:
            try:
                orders = await self.client.fetch_open_orders(symbol=s)
                all_orders.extend(orders)
            except Exception as e:
                logger.warning(f"[CCXT] fetch_open_orders({s}) failed: {e}")
        return all_orders

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetches active positions (primarily for futures; safely returns [] for spot)."""
        if self.mode == BotMode.PAPER:
            return []
        try:
            if hasattr(self.client, "fetch_positions"):
                await exchange_rate_limiter.acquire(weight=2.0)
                return await self.client.fetch_positions(symbols=symbols)
        except Exception as e:
            logger.info(f"[CCXT] fetch_positions skipped (Spot market mode or testnet): {e}")
            return []
        return []

    async def create_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        amount: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends an idempotent order to the exchange."""
        await exchange_rate_limiter.acquire(weight=2.0)
        params = {}
        if client_order_id:
            # Standard CCXT custom client order ID tag
            params["clientOrderId"] = client_order_id

        return await self.client.create_order(
            symbol=symbol,
            type=order_type.value,
            side=side.value,
            amount=float(amount),
            price=float(price) if price else None,
            params=params
        )

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancels an existing order on the exchange."""
        await exchange_rate_limiter.acquire(weight=1.0)
        return await self.client.cancel_order(order_id, symbol=symbol)

    async def close(self) -> None:
        """Closes CCXT async session."""
        if self.client:
            await self.client.close()
            self.is_initialized = False
