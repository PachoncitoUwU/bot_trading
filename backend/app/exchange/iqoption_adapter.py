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


MODERN_ACTIVE_IDS = {
    "EURUSD": 1861, "EURUSD-OP": 1861, "EURUSD-OTC": 1861,
    "GBPUSD": 1867, "GBPUSD-OP": 1867, "GBPUSD-OTC": 1867,
    "EURGBP": 1862, "EURGBP-OP": 1862, "EURGBP-OTC": 1862,
    "EURJPY": 1864, "EURJPY-OP": 1864, "EURJPY-OTC": 1864,
    "USDJPY": 1865, "USDJPY-OP": 1865, "USDJPY-OTC": 1865,
    "GBPJPY": 1866, "GBPJPY-OP": 1866, "GBPJPY-OTC": 1866,
    "NZDUSD": 1896, "NZDUSD-OP": 1896, "NZDUSD-OTC": 1896,
    "GBPCAD": 1897, "GBPCAD-OP": 1897, "GBPCAD-OTC": 1897,
    "USDCAD": 1878, "USDCAD-OP": 1878, "USDCAD-OTC": 1878,
}


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
            
            # Map modern active IDs (1860+ series) into OP_code.ACTIVES
            import iqoptionapi.constants as OP_code
            MODERN_ACTIVE_IDS = {
                "EURUSD": 1861, "EURUSD-OP": 1861, "EURUSD-OTC": 1861,
                "GBPUSD": 1867, "GBPUSD-OP": 1867, "GBPUSD-OTC": 1867,
                "EURGBP": 1862, "EURGBP-OP": 1862, "EURGBP-OTC": 1862,
                "EURJPY": 1864, "EURJPY-OP": 1864, "EURJPY-OTC": 1864,
                "USDJPY": 1865, "USDJPY-OP": 1865, "USDJPY-OTC": 1865,
                "GBPJPY": 1866, "GBPJPY-OP": 1866, "GBPJPY-OTC": 1866,
                "NZDUSD": 1896, "NZDUSD-OP": 1896, "NZDUSD-OTC": 1896,
                "GBPCAD": 1897, "GBPCAD-OP": 1897, "GBPCAD-OTC": 1897,
                "USDCAD": 1878, "USDCAD-OP": 1878, "USDCAD-OTC": 1878,
            }
            for k, v in MODERN_ACTIVE_IDS.items():
                OP_code.ACTIVES[k] = v
                OP_code.ACTIVES[k.lower()] = v
                OP_code.ACTIVES[k.upper()] = v
                clean = k.replace("-OP", "").replace("-op", "").replace("-OTC", "").replace("-otc", "").upper()
                OP_code.ACTIVES[clean] = v
                OP_code.ACTIVES[f"{clean}-op"] = v
                OP_code.ACTIVES[f"{clean}-OTC"] = v

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

            logger.info(f"[IQOPTION] Placing {action.upper()} on {active} for ${invest_amount} (Requested duration: {duration_minutes}m)...")
            instrument_type = "BINARY"
            candidates = []
            base_clean = active.replace("-OTC", "").replace("-OP", "")
            candidates.append(f"{base_clean}-op")
            candidates.append(active)
            candidates.append(base_clean)
            candidates.append(f"{base_clean}-OTC")
            
            # Deduplicate preserving order
            unique_candidates = []
            for c in candidates:
                if c not in unique_candidates:
                    unique_candidates.append(c)

            status = False
            order_id = None

            import iqoptionapi.constants as OP_code
            for cand in unique_candidates:
                clean_k = cand.replace("-op", "").replace("-OP", "").replace("-OTC", "").replace("-otc", "").upper()
                if clean_k in MODERN_ACTIVE_IDS:
                    OP_code.ACTIVES[cand] = MODERN_ACTIVE_IDS[clean_k]
                elif clean_k in OP_code.ACTIVES:
                    OP_code.ACTIVES[cand] = OP_code.ACTIVES[clean_k]
                elif cand not in OP_code.ACTIVES:
                    continue

                try:
                    # 1. Try with requested duration
                    status, order_id = await asyncio.to_thread(
                        self.client.buy, invest_amount, cand, action, duration_minutes
                    )
                    if status and order_id:
                        active = cand
                        symbol = cand
                        instrument_type = "BINARY"
                        logger.info(f"[IQOPTION] ✅ Order placed successfully on {cand} ({duration_minutes}m)! ID: {order_id}")
                        break

                    # 2. Try 1m turbo fallback
                    if duration_minutes != 1:
                        status, order_id = await asyncio.to_thread(
                            self.client.buy, invest_amount, cand, action, 1
                        )
                        if status and order_id:
                            active = cand
                            symbol = cand
                            instrument_type = "BINARY"
                            logger.info(f"[IQOPTION] ✅ Order placed successfully on {cand} (1m turbo)! ID: {order_id}")
                            break
                except KeyError:
                    continue
                
            # 4. Fallback: Try Digital Option with safe timeout (prevents infinite while loop in iqoptionapi)
            if not status and hasattr(self.client, "api") and self.client.api:
                logger.info(f"[IQOPTION] Binary options unavailable for {active}. Retrying with Digital Option...")
                try:
                    dig_status, dig_id = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._safe_buy_digital_spot, active, invest_amount, action, duration_minutes
                        ),
                        timeout=8.0
                    )
                    if dig_status and dig_id:
                        status = True
                        order_id = dig_id
                        instrument_type = "DIGITAL"
                        logger.info(f"[IQOPTION] Digital Option placed successfully! ID: {order_id}")
                except Exception as dig_err:
                    logger.debug(f"[IQOPTION] Digital option attempt failed: {dig_err}")

            if not status or not order_id:
                logger.warning(
                    f"[IQOPTION] ⚠️ Broker rejected order on {active} (market closed, instrument paused, or zero payout at this time)."
                )
                return {
                    "id": None,
                    "status": "rejected",
                    "symbol": symbol,
                    "instrument": instrument_type,
                    "reason": "BROKER_REJECTED"
                }

            logger.info(f"[IQOPTION] Order placed successfully! Instrument: {instrument_type} | Order ID: {order_id}")
            return {
                "id": str(order_id),
                "client_order_id": client_order_id,
                "symbol": symbol,
                "instrument": instrument_type,
                "side": side.value,
                "amount": invest_amount,
                "status": "filled",
                "price": float(price) if price else 0.0,
            }
        except Exception as e:
            logger.error(f"[IQOPTION] Order execution failed for {active}: {e}")
            return {
                "id": None,
                "status": "rejected",
                "symbol": symbol,
                "reason": str(e)
            }

    def _safe_buy_digital_spot(self, active: str, amount: float, action: str, duration: int) -> tuple:
        """Safe wrapper around digital options placement that avoids iqoptionapi's infinite while-loop."""
        if not self.client or not hasattr(self.client, "api") or not self.client.api:
            return False, None
        try:
            from datetime import datetime, timedelta
            from iqoptionapi.expiration import get_expiration_time
            dir_char = 'P' if action.lower() == 'put' else 'C'
            ts = int(self.client.api.timesync.server_timestamp)
            if duration == 1:
                exp, _ = get_expiration_time(ts, duration)
            else:
                now_date = datetime.fromtimestamp(ts) + timedelta(minutes=1, seconds=30)
                for _ in range(60):
                    if now_date.minute % duration == 0 and time.mktime(now_date.timetuple()) - ts > 30:
                        break
                    now_date += timedelta(minutes=1)
                exp = time.mktime(now_date.timetuple())

            date_str = str(datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M"))
            instrument_id = f"do{active}{date_str}PT{duration}M{dir_char}SPT"
            self.client.api.digital_option_placed_id = None
            self.client.api.place_digital_option(instrument_id, amount)

            start_wait = time.time()
            while self.client.api.digital_option_placed_id is None:
                if time.time() - start_wait > 5.0:  # Timeout estricto de 5s para nunca congelar
                    break
                time.sleep(0.1)

            placed_id = self.client.api.digital_option_placed_id
            if isinstance(placed_id, int):
                return True, placed_id
            return False, placed_id
        except Exception as e:
            logger.debug(f"[IQOPTION] Safe digital buy error: {e}")
            return False, None

    async def fetch_open_orders(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """IQ Option options close automatically on expiry."""
        return []

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Spot / Binary holding list."""
        return []

    async def check_order_result(self, order_id: str):
        """
        Polls IQ Option to see if the binary/digital option has expired and closed.
        Returns: (is_closed: bool, net_profit: float)
        """
        if not self.client or not str(order_id).isdigit():
            return False, 0.0
        try:
            oid = int(order_id)
            # 1. Check Binary Option with 5s timeout
            async_data = await asyncio.wait_for(
                asyncio.to_thread(self.client.get_async_order, oid),
                timeout=5.0
            )
            if async_data and async_data.get("option-closed") and async_data["option-closed"] != {}:
                msg = async_data["option-closed"].get("msg", {})
                profit = float(msg.get("profit_amount", 0.0)) - float(msg.get("amount", 0.0))
                return True, profit

            # 2. Check Digital Option with safe non-blocking check
            dig_res = await asyncio.wait_for(
                asyncio.to_thread(self._safe_check_win_digital, oid),
                timeout=5.0
            )
            if isinstance(dig_res, tuple) and len(dig_res) >= 2:
                is_closed, profit = dig_res[0], float(dig_res[1] or 0.0)
                if is_closed:
                    return True, profit
        except Exception as e:
            logger.debug(f"[IQOPTION] Error checking order {order_id} result: {e}")
        return False, 0.0

    def _safe_check_win_digital(self, buy_order_id: int) -> tuple:
        """Safe non-blocking checker for digital options that never enters infinite loops."""
        if not self.client or not hasattr(self.client, "get_async_order"):
            return False, 0.0
        try:
            start_w = time.time()
            while time.time() - start_w < 4.0:
                order_data_dict = self.client.get_async_order(buy_order_id)
                pos_changed = order_data_dict.get("position-changed", {})
                if pos_changed and pos_changed != {}:
                    order_data = pos_changed.get("msg")
                    if order_data and order_data.get("status") == "closed":
                        if order_data.get("close_reason") == "expired":
                            return True, float(order_data.get("close_profit", 0.0)) - float(order_data.get("invest", 0.0))
                        elif order_data.get("close_reason") == "default":
                            return True, float(order_data.get("pnl_realized", 0.0))
                    return False, 0.0
                time.sleep(0.2)
        except Exception:
            pass
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
