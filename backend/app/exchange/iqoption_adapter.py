"""IQ Option Adapter for Real-Time Demo and Real Trading.

Connects to the official IQ Option Websocket API, switches to PRACTICE (demo)
or REAL mode, fetches live candle streams, and executes binary/digital options.
"""
import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.constants import BotMode, OrderSide, OrderType
from app.core.decimal_math import to_decimal
from app.core.logger import logger

try:
    from iqoptionapi.stable_api import IQ_Option
    HAS_IQOPTION = True
except ImportError:
    HAS_IQOPTION = False


class IQOptionAdapter:
    """Standardized Exchange Adapter for IQ Option."""

    def __init__(self, mode: BotMode = BotMode.TESTNET):
        self.mode = mode
        self.email = settings.IQOPTION_EMAIL
        self.password = settings.IQOPTION_PASSWORD
        self.balance_type = settings.IQOPTION_BALANCE_MODE.upper()  # "PRACTICE" or "REAL"
        self.client: Optional[Any] = None
        self.is_initialized = False

    async def initialize(self) -> None:
        """Connects and authenticates with IQ Option."""
        if not HAS_IQOPTION:
            raise RuntimeError("iqoptionapi is not installed. Run: pip install iqoptionapi")

        if self.is_initialized and self.client:
            logger.info("[IQOPTION] Already connected and initialized.")
            return

        if not self.email or not self.password:
            logger.warning("[IQOPTION] Email or password not set in .env. Running in safe mode.")
            return

        logger.info(f"[IQOPTION] Connecting to IQ Option as {self.email} ({self.balance_type} mode)...")
        
        # IQ_Option connection is blocking; run in thread pool
        def _connect():
            api = IQ_Option(self.email, self.password)
            check, reason = api.connect()
            if not check:
                raise ConnectionError(f"IQ Option connection failed: {reason}")
            time.sleep(1.5)
            # Switch balance type: PRACTICE (Demo) or REAL
            api.change_balance(self.balance_type)
            time.sleep(1.0)
            return api

        try:
            self.client = await asyncio.to_thread(_connect)
            self.is_initialized = True
            bal = self.client.get_balance()
            logger.info(f"[IQOPTION] Successfully connected! Balance ({self.balance_type}): ${bal:,.2f}")
        except Exception as e:
            logger.error(f"[IQOPTION] Login failed: {e}")
            self.is_initialized = False
            raise

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """Returns the current account balance (USD / Practice Currency)."""
        if not self.is_initialized or not self.client:
            return {"USDT": Decimal("10000.00")}
        try:
            bal = await asyncio.to_thread(self.client.get_balance)
            dec_bal = to_decimal(bal)
            return {"USDT": dec_bal, "USD": dec_bal}
        except Exception as e:
            logger.error(f"[IQOPTION] fetch_balance error: {e}")
            return {"USDT": Decimal("10000.00")}

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 60
    ) -> List[list]:
        """
        Fetches live candles from IQ Option.
        Converts 'BTC/USDT' -> 'BTCUSD' or 'EUR/USD' -> 'EURUSD'.
        """
        if not self.is_initialized or not self.client:
            return []

        active = symbol.replace("/", "").upper()
        if active in ("BTCUSDT", "BTC/USDT"):
            active = "BTCUSD"

        # Timeframe in seconds: 1m -> 60, 5m -> 300, 15m -> 900
        tf_seconds = 60
        if timeframe == "5m":
            tf_seconds = 300
        elif timeframe == "15m":
            tf_seconds = 900
        elif timeframe == "1h":
            tf_seconds = 3600

        try:
            # Auto-reconnect if socket dropped
            if not self.client.check_connect():
                logger.info("[IQOPTION] Websocket dropped. Reconnecting...")
                await asyncio.to_thread(self.client.connect)
                await asyncio.to_thread(self.client.change_balance, self.balance_type)

            end_time = int(time.time())
            candles = await asyncio.to_thread(
                self.client.get_candles, active, tf_seconds, limit, end_time
            )
            # Format to CCXT standard: [timestamp_ms, open, high, low, close, volume]
            formatted = []
            for c in candles:
                formatted.append([
                    int(c["from"] * 1000),
                    float(c["open"]),
                    float(c["max"]),
                    float(c["min"]),
                    float(c["close"]),
                    float(c.get("volume", 0)),
                ])
            return formatted
        except Exception as e:
            logger.error(f"[IQOPTION] fetch_ohlcv failed for {symbol}: {e}")
            return []

    async def create_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        amount: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        duration_minutes: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes a binary option order (CALL / PUT) on IQ Option with customizable expiration.
        Shows up directly in the user's mobile app or traderoom!
        """
        if not self.is_initialized or not self.client:
            logger.warning("[IQOPTION] create_order called but adapter not initialized.")
            return {"id": "MOCK_IQ", "status": "closed", "price": price or 0}

        active = symbol.replace("/", "").upper()
        if active in ("BTCUSDT", "BTC/USDT"):
            active = "BTCUSD"

        action = "call" if side == OrderSide.BUY else "put"
        duration_minutes = max(1, min(15, int(duration_minutes or 1)))  # e.g., 1, 2, 3, 5m
        invest_amount = max(1.0, float(amount))

        try:
            # Ensure connection is fresh
            if not self.client.check_connect():
                logger.info("[IQOPTION] Reconnecting before placing order...")
                await asyncio.to_thread(self.client.connect)
                await asyncio.to_thread(self.client.change_balance, self.balance_type)

            logger.info(f"[IQOPTION] Placing {action.upper()} on {active} for ${invest_amount} (Duration: {duration_minutes}m)...")
            status, order_id = await asyncio.to_thread(
                self.client.buy, invest_amount, active, action, duration_minutes
            )
            if not status:
                raise RuntimeError(f"IQ Option rejected order on {active}")

            logger.info(f"[IQOPTION] Order placed successfully! Order ID: {order_id}")
            return {
                "id": str(order_id),
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side.value,
                "amount": invest_amount,
                "status": "filled",
                "price": float(price) if price else 0.0,
            }
        except Exception as e:
            logger.error(f"[IQOPTION] Order execution failed: {e}")
            raise

    async def fetch_open_orders(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """IQ Option options close automatically on expiry."""
        return []

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Spot / Binary holding list."""
        return []

    async def check_order_result(self, order_id: str):
        """
        Polls IQ Option to see if the binary option has expired and closed.
        Returns: (is_closed: bool, net_profit: float)
        """
        if not self.client or not str(order_id).isdigit():
            return False, 0.0
        try:
            oid = int(order_id)
            async_data = await asyncio.to_thread(self.client.get_async_order, oid)
            if async_data and async_data.get("option-closed") and async_data["option-closed"] != {}:
                msg = async_data["option-closed"].get("msg", {})
                profit = float(msg.get("profit_amount", 0.0)) - float(msg.get("amount", 0.0))
                return True, profit
        except Exception as e:
            logger.debug(f"[IQOPTION] Error checking order {order_id} result: {e}")
        return False, 0.0

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Binary options cannot be cancelled once submitted."""
        return False

    async def close(self) -> None:
        """Disconnects websocket."""
        if self.client and hasattr(self.client, "api"):
            try:
                self.client.api.close()
                logger.info("[IQOPTION] Disconnected safely.")
            except Exception:
                pass
        self.is_initialized = False
