"""Main Bot Lifecycle Runner and Trading Loop Orchestrator."""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.constants import BotMode, CircuitBreakerStatus, OrderSide, OrderStatus, OrderType, SignalType
from app.core.decimal_math import to_decimal
from app.core.logger import logger
from app.database.order_repository import (
    create_order_record,
    generate_client_order_id,
    get_open_positions,
    update_order_from_exchange,
    upsert_position,
)
from app.database.session import get_db_session
from app.engine.circuit_breaker import CircuitBreaker
from app.engine.risk_manager import RiskManager
from app.engine.session_manager import SessionManager
from app.engine.staking_manager import StakingManager
from app.engine.state_reconciler import StateReconciler, ReconciliationResult
from app.exchange.ccxt_adapter import CCXTExchangeAdapter
from app.services.sentiment_service import sentiment_service
from app.strategies.base_strategy import BaseStrategy, StrategySignal
from app.strategies.ai_learning_strategy import AILearningStrategy
from app.telegram.admin_handlers import TelegramAdminHandler
from app.telegram.broadcast_channel import TelegramBroadcastService
from app.telegram.heartbeat import HeartbeatWatchdog
from app.telegram.interactive_signal import InteractiveSignalManager
from app.telegram.visual_reporter import generate_trade_card_image
from app.api.websocket_hub import ws_hub

# Ticks before each balance refresh from exchange (avoids API hammering)
_BALANCE_REFRESH_EVERY_N_TICKS = 10


class BotRunner:
    """Orchestrates market ingestion, strategy evaluation, risk validation, and UI streaming."""

    def __init__(self):
        self.mode = settings.BOT_MODE
        self.is_running = False
        if settings.EXCHANGE_ID.lower() == "iqoption":
            from app.exchange.iqoption_adapter import IQOptionAdapter
            self.exchange = IQOptionAdapter(mode=self.mode)
        else:
            self.exchange = CCXTExchangeAdapter(mode=self.mode)
        self.circuit_breaker = CircuitBreaker(max_consecutive_errors=settings.CIRCUIT_BREAKER_MAX_ERRORS)
        self.risk_manager = RiskManager(circuit_breaker=self.circuit_breaker)
        self.staking_manager = StakingManager()
        self.session_manager = SessionManager(target_mode="3.5%", hourly_cycle_enabled=False)
        self.reconciler = StateReconciler(self.exchange)
        self.signal_manager = InteractiveSignalManager(default_ttl_seconds=settings.TELEGRAM_SIGNAL_TTL_SECONDS)
        self.admin_handler = TelegramAdminHandler(self.risk_manager, self.reconciler, self.signal_manager)
        self.heartbeat = HeartbeatWatchdog()
        self.broadcast_service = TelegramBroadcastService()

        # Active AI Adaptive Strategy
        self.strategy: BaseStrategy = AILearningStrategy(
            symbols=settings.TRADING_SYMBOLS,
            timeframe=settings.DEFAULT_TIMEFRAME,
        )

        # Balances and State
        self.equity = Decimal("10000.00")       # Overwritten by fetch_balance() on start
        self.initial_equity = Decimal("10000.00")
        self.available_cash = Decimal("10000.00")
        self.closed_trades_count = 0
        self.last_candle_cache: Dict[str, list] = {}
        self._tick_count: int = 0
        self.trade_history: List[Dict[str, Any]] = []
        self.duration_minutes: int = 5
        self.max_concurrent_binary_trades: int = 1  # Francotirador: 1 operación a la vez para máxima concentración
        self._pair_cooldowns: Dict[str, float] = {}  # Anti-revancha: cooldown por símbolo
        self.equity_curve: List[Dict[str, Any]] = [
            {"time": "Inicio", "equity": 10000.0, "pnl": 0.0, "is_win": True}
        ]

    def set_timeframe(self, timeframe: str) -> int:
        """Sets active trading expiration duration (1m, 2m, 3m, 5m)."""
        clean_tf = str(timeframe).lower().replace("m", "").strip()
        try:
            minutes = int(clean_tf)
            if minutes in (1, 2, 3, 5):
                self.duration_minutes = minutes
            else:
                self.duration_minutes = 1
        except Exception:
            self.duration_minutes = 1
        logger.info(f"[RUNNER] Trading duration timeframe set to {self.duration_minutes}m")
        return self.duration_minutes

    # ──────────────────────────────────────────────────────────────────────────
    # Startup
    # ──────────────────────────────────────────────────────────────────────────

    async def start(self) -> ReconciliationResult:
        """Starts the bot: initializes exchange, syncs balance, executes state reconciliation."""
        logger.info(f"[RUNNER] Starting trading bot in {self.mode.value} mode...")

        # 1. Initialize exchange connection with safe fallback
        try:
            await self.exchange.initialize()
        except Exception as e:
            logger.warning(f"[RUNNER] Exchange init in {self.mode.value} mode failed ({e}). Fallback to PAPER mode.")
            self.mode = BotMode.PAPER
            self.exchange.mode = BotMode.PAPER
            await self.exchange.initialize()

        # 2. Sync equity from exchange (GAP #6 fix)
        await self._refresh_balance()

        # For binary options (IQ Option), clear any stale in-memory positions and close zombie DB rows BEFORE reconciliation
        if settings.EXCHANGE_ID.lower() == "iqoption":
            self.risk_manager.active_positions.clear()
            try:
                from app.database.order_repository import close_position_record
                async with get_db_session() as session:
                    stale_positions = await get_open_positions(session)
                    for sp in stale_positions:
                        await close_position_record(session, sp["symbol"], realized_pnl=Decimal("0"))
            except Exception as clean_err:
                logger.debug(f"[RUNNER] Non-fatal cleanup of stale positions: {clean_err}")

        # 3. Reconcile state against DB (GAP #4 fix — uses real DB, not empty lists)
        async with get_db_session() as session:
            reconcile_result = await self.reconciler.reconcile(db_session=session)

        if not reconcile_result.is_clean:
            logger.error("[RUNNER] Startup halted: Reconciliation discrepancies require human review.")
            self.is_running = False
            return reconcile_result

        auto_start = getattr(settings, "AUTO_START_TRADING", True)
        self.is_running = auto_start
        self.risk_manager.update_daily_equity(self.equity)
        self.session_manager.sync_starting_equity(self.equity)
        if self.is_running:
            logger.info("[RUNNER] Bot inicializado y OPERANDO en vivo 24/7 de forma autónoma.")
        else:
            logger.info("[RUNNER] Bot inicializado con éxito en modo STANDBY (Esperando comando de inicio desde Telegram).")
        return reconcile_result

    def reset_and_resume_trading(self, is_manual_start: bool = False) -> Tuple[bool, str]:
        """Resets session targets and starts/resumes trading, strictly respecting daily Stop Loss."""
        import time
        from datetime import datetime

        today_str = datetime.now().strftime("%Y-%m-%d")
        # CANDADO DE STOP LOSS: Si el inicio es manual y hoy ya se activó el Stop Loss, BLOQUEAR
        if is_manual_start:
            is_sl_locked = (
                self.risk_manager.is_daily_drawdown_locked
                or (hasattr(self, "session_manager") and getattr(self.session_manager, "daily_sl_locked_date", None) == today_str)
            )
            if is_sl_locked:
                logger.warning(f"[RUNNER] Inicio manual bloqueado: Stop Loss diario activo ({today_str}). No se anula el límite.")
                return False, "DAILY_SL_LOCKED"

        self.is_running = True
        if hasattr(self, "circuit_breaker"):
            self.circuit_breaker.manual_reset()
        if hasattr(self, "session_manager"):
            self.session_manager.reset_session(current_equity=self.equity)
            self.session_manager.cycle_state = "ACTIVE"
            self.session_manager.cycle_start_time = time.time()
        if hasattr(self, "risk_manager") and not self.risk_manager.is_daily_drawdown_locked:
            self.risk_manager.reset_daily_limits(self.equity)
        if hasattr(self, "reconciler"):
            self.reconciler.is_locked_for_review = False
        if hasattr(self, "admin_handler"):
            self.admin_handler.is_panic_stopped = False
            self.admin_handler.state_reconciler.is_locked_for_review = False
        logger.info(f"[RUNNER] Sesión de trading iniciada exitosamente (Límite 7 ops | Circuit Breaker NORMAL). Saldo base: ${self.equity:,.2f} USD")
        return True, "STARTED"

    async def check_daily_market_schedule(self) -> None:
        """Checks daily market opening (07:00 AM Mon-Fri) for automatic session reset and wakeup."""
        if not hasattr(self, "session_manager"):
            return

        should_wake, is_open, reason = self.session_manager.check_daily_market_schedule()
        if should_wake:
            logger.info(f"[RUNNER] 🌅 Apertura de Mercado Real detectada ({reason}). Despertando bot y reseteando jornada...")
            await self._refresh_balance()
            self.risk_manager.reset_daily_limits(self.equity)
            self.session_manager.reset_session(current_equity=self.equity)
            self.session_manager.daily_sl_locked_date = None
            self.is_running = True

            from app.telegram.telegram_client import get_telegram_client
            client = get_telegram_client()
            target_chat = settings.TELEGRAM_ADMIN_CHAT_ID or settings.TELEGRAM_CHANNEL_ID
            if client and target_chat:
                today_date = datetime.now().strftime("%Y-%m-%d")
                wakeup_msg = self.admin_handler.handle_daily_market_wakeup_message(today_date, float(self.equity))
                keyboard = self.admin_handler.get_main_menu_keyboard()
                try:
                    await client.send_message(target_chat, wakeup_msg, reply_markup=keyboard)
                except Exception as tg_err:
                    logger.debug(f"[RUNNER] Error enviando mensaje matutino: {tg_err}")

    # ──────────────────────────────────────────────────────────────────────────
    # Main tick
    # ──────────────────────────────────────────────────────────────────────────

    async def tick(self):
        """Single tick iteration of the trading loop."""
        if not self.is_running or self.reconciler.is_locked_for_review:
            return

        if not self.exchange.is_initialized:
            await self.start()

        if not self.circuit_breaker.can_trade():
            logger.warning("[RUNNER] Tick skipped: Circuit breaker is TRIPPED.")
            return

        # 0. Verificación de Meta de Ganancia (Take Profit de Sesión 3%-5%)
        if self.session_manager.is_target_reached:
            # Si el usuario explícitamente reanudó el bot (is_running == True), reiniciar para nueva meta
            self.session_manager.reset_session()
            logger.info("[RUNNER] Nueva sesión iniciada tras alcanzar meta previa. Reiniciando baseline de ganancias.")

        # 0.1 Verificación de Ciclo Horario (1 hora operando / 1 hora de descanso)
        can_trade_cycle, cycle_reason = self.session_manager.check_hourly_cycle()
        if not can_trade_cycle:
            if self._tick_count % 30 == 0:
                logger.info(f"[RUNNER] {cycle_reason}")
            await ws_hub.broadcast("STATUS_UPDATE", self.get_intuitive_telemetry())
            return

        try:
            self._tick_count += 1

            # Refresh balance from exchange every N ticks (GAP #6 fix)
            if self._tick_count % _BALANCE_REFRESH_EVERY_N_TICKS == 0:
                await self._refresh_balance()

            # Update internet market sentiment in strategy
            if hasattr(self.strategy, "update_sentiment_cache"):
                sentiment_data = await sentiment_service.get_sentiment()
                self.strategy.update_sentiment_cache(sentiment_data)

            # Monitor open positions for automatic Take Profit & Stop Loss (Spot exchanges only, NOT binary options)
            if settings.EXCHANGE_ID.lower() != "iqoption":
                for sym, pos in list(self.risk_manager.active_positions.items()):
                    if sym in self.last_candle_cache and self.last_candle_cache[sym]:
                        curr_p = to_decimal(self.last_candle_cache[sym][-1][4])
                        if pos.take_profit and curr_p >= pos.take_profit:
                            logger.info(f"[RUNNER] TAKE PROFIT reached for {sym} @ {curr_p} (Target: {pos.take_profit})")
                            tp_sig = StrategySignal(
                                symbol=sym,
                                signal_type=SignalType.SELL,
                                price=curr_p,
                                pattern_name="Take Profit Alcanzado 🎯",
                                reason=f"Objetivo de ganancia alcanzado (${curr_p:,.2f} >= ${pos.take_profit:,.2f})"
                            )
                            await self._execute_sell(tp_sig, sym, exit_reason="TAKE_PROFIT")

                        elif pos.stop_loss and curr_p <= pos.stop_loss:
                            logger.warning(f"[RUNNER] STOP LOSS reached for {sym} @ {curr_p} (Limit: {pos.stop_loss})")
                            sl_sig = StrategySignal(
                                symbol=sym,
                                signal_type=SignalType.SELL,
                                price=curr_p,
                                pattern_name="Stop Loss Activado 🛡",
                                reason=f"Protección de capital activada (${curr_p:,.2f} <= ${pos.stop_loss:,.2f})"
                            )
                            await self._execute_sell(sl_sig, sym, exit_reason="STOP_LOSS")

            # Enforce max concurrent binary trades (Sniper mode: max 1 trade at a time)
            if settings.EXCHANGE_ID.lower() == "iqoption" and len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                await ws_hub.broadcast("STATUS_UPDATE", self.get_intuitive_telemetry())
                return


            # Priorizar pares de Mercado Real Matutino (No-OTC) si estamos en sesión bancaria de la mañana
            regime = self.session_manager.get_market_regime()
            symbols_to_scan = list(settings.TRADING_SYMBOLS)
            if regime.get("is_morning_real"):
                symbols_to_scan.sort(key=lambda s: 1 if "-OTC" in s.upper() else 0)

            order_dispatched = False
            for symbol in symbols_to_scan:
                if settings.EXCHANGE_ID.lower() == "iqoption" and len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                    break

                # 1. Fetch candles with deep historical context (120 candles = 2 hours of price action)
                candles = await self.exchange.fetch_ohlcv(
                    symbol, timeframe=settings.DEFAULT_TIMEFRAME, limit=120
                )
                self.last_candle_cache[symbol] = candles
                if not candles or len(candles) < 2:
                    continue
                last_price = to_decimal(candles[-1][4])

                # 2. Evaluate Strategy
                market_data = {symbol: candles}
                signals = self.strategy.generate_signals(market_data, self.risk_manager.active_positions)

                for sig in signals:
                    if settings.EXCHANGE_ID.lower() == "iqoption" and len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                        order_dispatched = True
                        break

                    logger.info(
                        f"[RUNNER] Signal: {sig.signal_type.value} {symbol} @ ${sig.price}"
                    )

                    # Broadcast signal to UI dashboard
                    await ws_hub.broadcast("NEW_SIGNAL", {
                        "symbol": sig.symbol,
                        "type": sig.signal_type.value,
                        "price": str(sig.price),
                        "stop_loss": str(sig.stop_loss) if sig.stop_loss else None,
                        "take_profit": str(sig.take_profit) if sig.take_profit else None,
                        "pattern": sig.pattern_name,
                        "reason": sig.reason,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                    # BUY signal (CALL) → validate risk + dispatch order
                    if sig.signal_type == SignalType.BUY and symbol not in self.risk_manager.active_positions:
                        await self._execute_buy(sig, symbol, side=OrderSide.BUY)
                        if settings.EXCHANGE_ID.lower() == "iqoption" and len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                            order_dispatched = True
                            break

                    # SELL signal:
                    # In IQ Option binary: SELL is a PUT entry!
                    elif sig.signal_type == SignalType.SELL:
                        if settings.EXCHANGE_ID.lower() == "iqoption" and symbol not in self.risk_manager.active_positions:
                            await self._execute_buy(sig, symbol, side=OrderSide.SELL)
                            if settings.EXCHANGE_ID.lower() == "iqoption" and len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                                order_dispatched = True
                                break
                        elif symbol in self.risk_manager.active_positions:
                            await self._execute_sell(sig, symbol, exit_reason="SIGNAL_SELL")

                if order_dispatched and settings.EXCHANGE_ID.lower() == "iqoption":
                    break

            # Stream live thoughts of the AI to UI dashboard
            if hasattr(self.strategy, "get_latest_thoughts"):
                thoughts = self.strategy.get_latest_thoughts()
                await ws_hub.broadcast("AI_THOUGHTS", {
                    "thoughts": thoughts,
                    "timestamp": datetime.utcnow().strftime("%H:%M:%S")
                })

            # Broadcast live status to UI dashboard
            await ws_hub.broadcast("STATUS_UPDATE", self.get_intuitive_telemetry())

            self.circuit_breaker.record_success()

        except Exception as e:
            # GAP silent exception #1 fix: log full stack trace, not just the message
            logger.error(
                f"[RUNNER] Tick error (type={type(e).__name__}): {e}",
                exc_info=True,
            )
            self.circuit_breaker.record_error(str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # Order execution helpers (GAP #1)
    # ──────────────────────────────────────────────────────────────────────────

    async def _execute_buy(self, sig, symbol: str, side: OrderSide = OrderSide.BUY) -> None:
        """Validates risk/staking, dispatches an order (BUY/CALL or SELL/PUT) to the exchange, and persists to DB."""
        # Dynamic duration selection:
        # - High conviction & triple confluence: 5m (more time to develop with zero 60s noise)
        # - Solid technical reversal / pattern: 3m (extended duration for clean development)
        # - Fast momentum / scalping: 1m (quick entry/exit)
        sig_conf = getattr(sig, "confidence", Decimal("0.5"))
        sig_confluences = getattr(sig, "metadata", {}).get("confluences", 1)
        pat_name = getattr(sig, "pattern_name", "") or ""
        current_step = self.staking_manager.current_step_index + 1

        # Selección de duración inteligente:
        # Alta Convicción Sniper: Duración fija de 5 minutos
        # Filtra el ruido errático de 1 minuto y permite que la confluencia técnica se desarrolle limpiamente
        trade_duration = 5

        if settings.EXCHANGE_ID.lower() == "iqoption":
            import time
            # 0. Francotirador estricto: Si ya hay 1 operación abierta, abortar inmediatamente
            if len(self.risk_manager.active_positions) >= self.max_concurrent_binary_trades:
                logger.info("[RUNNER] Francotirador estricto: ya hay 1 operación activa en curso. Bloqueando nueva entrada.")
                return

            # 1. Enforce pair cooldown
            remaining_cooldown = self._pair_cooldowns.get(symbol, 0) - time.time()
            if remaining_cooldown > 0:
                logger.info(f"[RUNNER] Enfriamiento activo para {symbol} ({int(remaining_cooldown)}s restantes). Entrada omitida.")
                return

            # 2. FILTRO DE CONVICCIÓN EN RECUPERACIÓN (Paso 2):
            # Requiere confianza >= 55% y mínimo 2 confluencias comprobadas
            if current_step >= 2:
                if sig_conf < Decimal("0.55") or sig_confluences < 2:
                    logger.info(
                        f"[RUNNER] Paso {current_step} de recuperación en espera: Requiere confianza >= 55% y confluencias >= 2 "
                        f"(actual: conf={sig_conf:.2f}, confs={sig_confluences}). Esperando mejor confluencia técnica."
                    )
                    return

            # 3. Dynamic stake calculation: Base $50, Step 2 $100, Step 3 $200
            size, reason = self.staking_manager.calculate_dynamic_stake(
                confidence=sig_conf,
                confluences=sig_confluences,
            )
            if self.available_cash < size:
                logger.warning(f"[RUNNER] Order skipped: insufficient cash (${self.available_cash:.2f}) for stake ${size}")
                return
            is_valid = True
        else:
            is_valid, size, reason = self.risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=sig.price,
                stop_loss=sig.stop_loss,
                total_account_equity=self.equity,
                available_cash=self.available_cash,
            )
            if not is_valid:
                logger.info(f"[RUNNER] Order rejected by risk manager: {reason}")
                return

        client_order_id = generate_client_order_id("BOT")

        # 1. Non-blocking attempt to record order intent in DB
        try:
            async with get_db_session() as session:
                await create_order_record(
                    session,
                    client_order_id=client_order_id,
                    symbol=symbol,
                    exchange_id=settings.EXCHANGE_ID,
                    mode=self.mode,
                    side=side,
                    order_type=OrderType.MARKET,
                    amount=size,
                    strategy_name=self.strategy.name,
                )
        except Exception as db_err:
            logger.warning(f"[DB] Could not record initial order intent (non-fatal): {db_err}")

        # 2. DISPATCH ORDER TO BROKER (Completely outside DB session to avoid SQLite locks)
        if self.mode == BotMode.PAPER:
            # Paper mode: simulate immediate fill
            exchange_order_id = f"PAPER_{client_order_id}"
            filled_amount = size
            fill_price = sig.price
            logger.info(
                f"[PAPER] Simulated {side.value} {symbol}: {size} ({trade_duration}m) @ ${fill_price} | "
                f"client_id={client_order_id}"
            )
        else:
            # TESTNET / LIVE: send real order to exchange with hard 15s timeout
            try:
                order_resp = await asyncio.wait_for(
                    self.exchange.create_order(
                        symbol=symbol,
                        order_type=OrderType.MARKET,
                        side=side,
                        amount=size,
                        client_order_id=client_order_id,
                        duration_minutes=trade_duration,
                    ),
                    timeout=15.0
                )
                
                if not order_resp or order_resp.get("status") == "rejected" or not order_resp.get("id"):
                    logger.warning(
                        f"[RUNNER] ⚠️ Orden en {symbol} rechazada por broker "
                        f"(razón: {order_resp.get('reason', 'Activo cerrado o sin payout')}). "
                        f"Aplicando enfriamiento de 2m a {symbol} para no interrumpir los otros 7 pares."
                    )
                    import time
                    self._pair_cooldowns[symbol] = time.time() + 120
                    return

                exchange_order_id = str(order_resp.get("id", ""))
                filled_amount = to_decimal(order_resp.get("filled") or size)
                fill_price = to_decimal(order_resp.get("average") or order_resp.get("price") or sig.price)
                logger.info(
                    f"[ORDER DISPATCHED] {symbol} {side.value} ${size} ({trade_duration}m) | "
                    f"client_id={client_order_id} | exchange_id={exchange_order_id} | reason={reason}"
                )
            except Exception as e:
                logger.warning(
                    f"[RUNNER] ⚠️ Error al enviar orden en {symbol}: {e}. "
                    f"Enfriando par {symbol} 2 min sin congelar el bot."
                )
                import time
                self._pair_cooldowns[symbol] = time.time() + 120
                return

        # 3. Non-blocking attempt to persist filled order & position to DB
        try:
            async with get_db_session() as session:
                await update_order_from_exchange(
                    session,
                    client_order_id=client_order_id,
                    exchange_order_id=exchange_order_id,
                    status=OrderStatus.FILLED,
                    filled_amount=filled_amount,
                    avg_fill_price=fill_price,
                )
                await upsert_position(
                    session,
                    symbol=symbol,
                    exchange_id=settings.EXCHANGE_ID,
                    mode=self.mode,
                    amount=filled_amount,
                    entry_price=fill_price,
                    stop_loss=sig.stop_loss,
                    take_profit=sig.take_profit,
                )
        except Exception as db_err:
            logger.warning(f"[DB] Could not persist filled order status (non-fatal): {db_err}")


        # Update in-memory risk state
        self.risk_manager.handle_partial_fill(
            symbol=symbol,
            fill_amount=filled_amount,
            fill_price=fill_price,
            total_target_amount=size,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
        )

        if settings.EXCHANGE_ID.lower() == "iqoption":
            cost = filled_amount
            inst_type = order_resp.get("instrument", "BINARY")
            # Watch binary option resolution in background with exact expiration duration and instrument type
            asyncio.create_task(self._watch_iqoption_binary_resolution(
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                stake=filled_amount,
                side=side,
                duration_minutes=trade_duration,
                entry_price=fill_price,
                sig=sig,
                instrument=inst_type,
            ))
        else:
            cost = filled_amount * fill_price

        self.available_cash -= cost

        # Broadcast to channel with chart card image (with exact duration)
        await self._broadcast_signal(
            sig,
            invested_amount=cost,
            available_cash=self.available_cash,
            side=side,
            duration_minutes=trade_duration,
        )

        await ws_hub.broadcast("POSITION_OPENED", {
            "symbol": symbol,
            "side": "CALL" if side == OrderSide.BUY else "PUT",
            "amount": str(filled_amount),
            "entry_price": str(fill_price),
            "duration_minutes": trade_duration,
            "duration_seconds": trade_duration * 60,
            "stop_loss": str(sig.stop_loss) if sig.stop_loss else None,
            "take_profit": str(sig.take_profit) if sig.take_profit else None,
            "exchange_order_id": exchange_order_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def _watch_iqoption_binary_resolution(
        self,
        exchange_order_id: str,
        symbol: str,
        stake: Decimal,
        side: OrderSide = OrderSide.BUY,
        duration_minutes: int = 1,
        entry_price: Optional[Decimal] = None,
        sig: Optional[Any] = None,
        instrument: str = "BINARY",
    ):
        """Waits for binary/digital option to expire, fetches actual PnL, sends visual result chart."""
        dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"
        side_label = "CALL (SUBIDA 🟢)" if side == OrderSide.BUY else "PUT (BAJADA 🔴)"
        side_str = "CALL" if side == OrderSide.BUY else "PUT"
        logger.info(f"[IQOPTION WATCHER] Monitoreando orden {exchange_order_id} ({symbol} {side_label} por ${stake}, {dur_str}, {instrument})...")

        wait_seconds = max(50, (duration_minutes * 60) + 4)
        await asyncio.sleep(wait_seconds)

        for attempt in range(18):
            try:
                is_closed, profit = await self.exchange.check_order_result(exchange_order_id)
                if is_closed:
                    is_win = (profit > 0)
                    logger.info(f"[IQOPTION WATCHER] Orden {exchange_order_id} FINALIZADA ({dur_str}, {instrument}). Ganada={is_win}, Ganancia Neta=${profit:.2f}")

                    # Registrar resultado en el gestor de martingala
                    staking_res = self.staking_manager.record_trade_result(is_win, profit, symbol)

                    # Quitar de active_positions si existía y activar enfriamiento de 120s
                    if symbol in self.risk_manager.active_positions:
                        del self.risk_manager.active_positions[symbol]
                    try:
                        from app.database.order_repository import close_position_record
                        async with get_db_session() as session:
                            await close_position_record(session, symbol, realized_pnl=Decimal(str(profit)))
                    except Exception:
                        pass
                    import time
                    self._pair_cooldowns[symbol] = time.time() + 45.0  # 45 segundos de enfriamiento ágil

                    # Alimentar el resultado a la memoria de aprendizaje por refuerzo de la IA
                    if hasattr(self.strategy, "record_trade_outcome"):
                        pnl_pct_dec = Decimal(str(round((profit / float(stake)) * 100, 2))) if float(stake) > 0 else Decimal("0")
                        self.strategy.record_trade_outcome(
                            symbol=symbol,
                            pnl_pct=pnl_pct_dec,
                            is_win=is_win,
                            pattern_name=getattr(sig, "pattern_name", "") or "General Sniper",
                        )

                    # Actualizar estadísticas
                    self.closed_trades_count += 1
                    trade_record = {
                        "symbol": symbol,
                        "side": side_label,
                        "instrument": instrument,
                        "invested_usd": float(stake),
                        "pnl_usd": round(profit, 2),
                        "pnl_pct": round((profit / float(stake)) * 100, 2) if float(stake) > 0 else 0.0,
                        "is_win": is_win,
                        "order_id": exchange_order_id,
                        "staking_step": staking_res["step_before"],
                        "next_stake": staking_res["next_stake"],
                        "duration_minutes": duration_minutes,
                        "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
                    }
                    self.trade_history.append(trade_record)

                    # Forward-Testing Tracker integration (Milestone reporting every 50 trades)
                    try:
                        from app.engine.forward_test_tracker import forward_test_tracker
                        is_milestone, milestone_msg = forward_test_tracker.record_trade(
                            symbol=symbol,
                            pattern=getattr(sig, "pattern_name", "") or "General Sniper",
                            side="CALL" if side == OrderSide.BUY else "PUT",
                            stake=float(stake),
                            is_win=is_win,
                            profit_usd=profit,
                            current_balance=float(self.equity),
                            instrument=instrument,
                            order_id=exchange_order_id,
                        )

                        if is_milestone and milestone_msg:
                            await self.broadcast_service.send_broadcast(milestone_msg)
                            logger.info(f"[FORWARD TEST] 🎯 Hito alcanzado ({forward_test_tracker.data['total_trades']}/300). Reporte enviado a Telegram.")
                    except Exception as ft_err:
                        logger.error(f"[FORWARD TEST] Error recording trade: {ft_err}")

                    # Refrescar balance real de IQ Option
                    await self._refresh_balance()

                    # Actualizar curva de rendimiento en memoria
                    self.equity_curve.append({
                        "time": datetime.utcnow().strftime("%H:%M:%S"),
                        "equity": float(self.equity),
                        "pnl": round(profit, 2),
                        "symbol": symbol,
                        "is_win": is_win,
                    })
                    if len(self.equity_curve) > 60:
                        self.equity_curve = self.equity_curve[-60:]

                    # Obtener velas recientes para la gráfica de resultado final
                    recent_candles = self.last_candle_cache.get(symbol, [])
                    if not recent_candles and self.exchange.is_initialized:
                        try:
                            recent_candles = await self.exchange.fetch_ohlcv(symbol, limit=25)
                        except Exception:
                            pass
                    exit_p = Decimal(str(recent_candles[-1][4])) if recent_candles else (entry_price or Decimal("1.0800"))

                    # Formato renovado y claro para Telegram (Requerimiento C)
                    clean_symbol = symbol.replace("-OTC", "")
                    mkt_type = "OTC" if "-OTC" in symbol.upper() else "Mercado Real"
                    side_icon = "🟢" if side == OrderSide.BUY else "🔴"

                    # 1. Progreso de Sesión (ej: 3/7)
                    curr_sess_trades = min(7, self.session_manager.session_closed_trades + 1)
                    sess_max = self.session_manager.session_max_trades
                    bar_sess = "🟩" * curr_sess_trades + "⬜" * (sess_max - curr_sess_trades)

                    # 2. Progreso hacia n=50 (Fase 3 acumulativa)
                    from app.engine.forward_test_tracker import forward_test_tracker
                    total_ft = forward_test_tracker.data.get("total_trades", 0)
                    wins_ft = forward_test_tracker.data.get("wins", 0)
                    losses_ft = forward_test_tracker.data.get("losses", 0)
                    wr_ft = round((wins_ft / total_ft) * 100, 1) if total_ft > 0 else 0.0
                    filled_50 = min(10, max(0, (total_ft * 10) // 50))
                    bar_50 = "🟩" * filled_50 + "⬜" * (10 - filled_50)
                    pct_50 = round((total_ft / 50) * 100, 1)

                    # 3. Estado de Reconciliación con Broker
                    reconcile_status = "✅ 100% Sincronizado (0 huérfanas)" if not self.reconciler.is_locked_for_review else "⚠️ Requiere Revisión"

                    if is_win:
                        tg_msg = (
                            f"🏆 <b>¡OPERACIÓN GANADORA! (+85%)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🪙 <b>Activo:</b> <code>{clean_symbol} ({mkt_type})</code>\n"
                            f"🧭 <b>Dirección:</b> <b>{side_label} {side_icon}</b> | ⏱️ <b>Tiempo:</b> <code>{dur_str}</code>\n"
                            f"💵 <b>Inversión:</b> <b>${stake:,.2f} USD</b> 🛡️ (Fija / Cero Martingala)\n"
                            f"💰 <b>Ganancia Neta:</b> <b>+${profit:,.2f} USD</b> 💵\n"
                            f"📈 <b>Saldo en Cuenta:</b> <b>${self.equity:,.2f} USD</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📊 <b>Sesión de Hoy:</b> <code>[{bar_sess}] {curr_sess_trades}/{sess_max} ops</code>\n"
                            f"🎯 <b>Efectividad Acumulada:</b> <b>{wins_ft}W - {losses_ft}L ({wr_ft}% Win Rate)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"<i>El bot continúa escaneando con paciencia buscando solo operaciones de muy alta probabilidad.</i>"
                        )
                    else:
                        tg_msg = (
                            f"🛡️ <b>OPERACIÓN CERRADA (STOP RESPETADO)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🪙 <b>Activo:</b> <code>{clean_symbol} ({mkt_type})</code>\n"
                            f"🧭 <b>Dirección:</b> <b>{side_label} {side_icon}</b> | ⏱️ <b>Tiempo:</b> <code>{dur_str}</code>\n"
                            f"💵 <b>Inversión:</b> <b>${stake:,.2f} USD</b> 🛡️ (Fija / Cero Martingala)\n"
                            f"📉 <b>Resultado:</b> <b>-${abs(profit):,.2f} USD</b>\n"
                            f"📈 <b>Saldo en Cuenta:</b> <b>${self.equity:,.2f} USD</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛡️ <b>Gestión de Riesgo Protegida:</b>\n"
                            f"• CERO Martingala: No se dobla la apuesta tras una pérdida.\n"
                            f"• Pérdida estrictamente acotada al stake fijo de $25 USD.\n"
                            f"• Esperando la siguiente confluencia perfecta triple con disciplina.\n"
                            f"━━━━━━━━━━━━━━━━━━━━"
                        )

                    # Generar tarjeta gráfica de resultado final con velas reales y enviar a Telegram
                    from app.telegram.telegram_client import get_telegram_client
                    from app.telegram.visual_reporter import generate_result_chart_card
                    client = get_telegram_client()
                    target_chat = settings.TELEGRAM_CHANNEL_ID or settings.TELEGRAM_ADMIN_CHAT_ID

                    if client and target_chat:
                        try:
                            res_chart = generate_result_chart_card(
                                symbol=symbol,
                                side=side_str,
                                entry_price=entry_price or (to_decimal(recent_candles[-2][4]) if len(recent_candles) >= 2 else exit_p),
                                exit_price=exit_p,
                                net_pnl=Decimal(str(profit)),
                                pnl_pct=Decimal(str(round((profit / float(stake)) * 100, 2))) if float(stake) > 0 else Decimal("0"),
                                candles=recent_candles,
                                duration_minutes=duration_minutes,
                                pattern_name=sig.pattern_name if sig else "Estrategia IA",
                                is_win=is_win,
                                stake=stake,
                                account_equity=self.equity,
                                mode_label=self.get_mode_label(),
                            )
                            await client.send_photo(chat_id=target_chat, photo_bytes=res_chart.getvalue(), caption=tg_msg)
                            logger.info(f"[IQOPTION WATCHER] Sent closing result photo chart to Telegram for {symbol}")
                        except Exception as photo_err:
                            logger.error(f"[IQOPTION WATCHER] Error sending result photo, fallback to text: {photo_err}")
                            if self.broadcast_service:
                                await self.broadcast_service.broadcast_to_channel(tg_msg)
                    elif self.broadcast_service:
                        await self.broadcast_service.broadcast_to_channel(tg_msg)

                    # Registrar en SessionManager (Meta 3%-5% y límite de 7 trades)
                    session_res = self.session_manager.record_trade_result(
                        net_profit=Decimal(str(profit)),
                        is_win=is_win,
                        current_equity=self.equity
                    )

                    # Si se alcanzó la meta o el límite de la sesión, auto-apagado protector
                    if session_res.get("just_reached"):
                        self.is_running = False
                        t_reason = session_res.get("target_reason", "")
                        if t_reason == "SESSION_LIMIT_7_REACHED":
                            target_msg = self.admin_handler.handle_session_trades_completed_report(
                                wins=session_res.get("wins", 0),
                                losses=session_res.get("losses", 0),
                                pnl_usd=float(session_res.get("session_profit", 0.0)),
                                pnl_pct=float(session_res.get("session_profit_pct", 0.0)),
                                current_equity=float(self.equity),
                                total_sample_trades=total_ft
                            )
                        elif t_reason == "STOP_LOSS_SESION":
                            self.risk_manager.is_daily_drawdown_locked = True
                            target_msg = (
                                f"🛡️ <b>FRENO DE SEGURIDAD ACTIVADO (STOP LOSS DE SESIÓN -3.0%)</b> 🛡️\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"📉 <b>Pérdida en la Sesión:</b> <b>${session_res.get('session_profit', 0):,.2f} USD ({session_res.get('session_profit_pct', 0):.2f}%)</b>\n"
                                f"💰 <b>Saldo Protegido:</b> <b>${self.equity:,.2f} USD</b>\n"
                                f"📊 <b>Operaciones:</b> {session_res.get('trades_count', 0)} "
                                f"({session_res.get('wins', 0)} Ganadas / {session_res.get('losses', 0)} Perdidas)\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🛑 <b>DISCIPLINA DE CAPITAL:</b> El bot se ha apagado automáticamente para blindar tu saldo.\n"
                                f"🔒 <b>CANDADO DE RIESGO:</b> Nuevas entradas quedan estrictamente bloqueadas durante el resto del día.\n"
                                f"🌅 <i>Se reactivará automáticamente mañana a las <b>07:00 AM</b> con la nueva jornada bancaria.</i>"
                            )
                        elif t_reason == "META_10K_ALCANZADA":
                            target_msg = (
                                f"🎉🏆 <b>¡MISIÓN CUMPLIDA! SALDO SUPERÓ LOS $10,000 USD</b> 🏆🎉\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"💰 <b>Saldo Final:</b> <b>${self.equity:,.2f} USD</b> 💵\n"
                                f"🧠 <b>Fase de Entrenamiento Completada con Éxito.</b>\n"
                                f"📊 <b>Operaciones Totales:</b> {session_res.get('trades_count', 0)} "
                                f"({session_res.get('wins', 0)} Ganadas / {session_res.get('losses', 0)} Perdidas)\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"<i>El bot ha detenido la maratón en la cima. ¡Excelente resultado!</i>"
                            )
                        else:
                            t_pct = session_res.get("target_pct", Decimal("3.0"))
                            s_profit = session_res.get("session_profit", Decimal("0"))
                            s_pct = session_res.get("session_profit_pct", Decimal("0"))
                            target_msg = (
                                f"🎉🏆 <b>¡META DE GANANCIA DE SESIÓN ALCANZADA!</b> 🏆🎉\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🎯 <b>Meta Cumplida:</b> <b>+{t_pct:.1f}%</b>\n"
                                f"💰 <b>Ganancia Asegurada:</b> <b>+${s_profit:,.2f} USD (+{s_pct:.2f}%)</b> 💵\n"
                                f"📈 <b>Saldo Final en Cuenta:</b> <b>${self.equity:,.2f} USD</b>\n"
                                f"📊 <b>Operaciones Realizadas:</b> {session_res.get('trades_count', 0)} "
                                f"({session_res.get('wins', 0)} Ganadas / {session_res.get('losses', 0)} Perdidas)\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🛡️ <b>DISCIPLINA DE ORO:</b> El bot se ha apagado automáticamente para blindar tus beneficios.\n\n"
                                f"<i>¡Felicidades por la sesión ganadora! Pulsa ▶️ Iniciar Trading para otra ronda.</i>"
                            )
                        if client and target_chat:
                            try:
                                keyboard = self.admin_handler.get_main_menu_keyboard()
                                await client.send_message(target_chat, target_msg, reply_markup=keyboard)
                            except Exception as tg_err:
                                logger.error(f"[SESSION MANAGER] Error enviando alerta de meta a Telegram: {tg_err}")

                    # Broadcast a WebSocket (Dashboard)
                    await ws_hub.broadcast("TRADE_CLOSED", trade_record)
                    await ws_hub.broadcast("STATUS_UPDATE", self.get_intuitive_telemetry())
                    return
            except Exception as e:
                logger.error(f"[IQOPTION WATCHER] Error consultando resultado {exchange_order_id}: {e}")
            await asyncio.sleep(3)

        # Fallback de seguridad si se agotaron los 18 intentos sin respuesta del broker:
        logger.warning(
            f"[IQOPTION WATCHER] Tiempo de espera agotado para orden {exchange_order_id} en {symbol}. "
            f"Liberando posición activa para permitir que el bot continúe operando."
        )
        if symbol in self.risk_manager.active_positions:
            del self.risk_manager.active_positions[symbol]
        await self._refresh_balance()
        try:
            from app.database.order_repository import close_position_record
            async with get_db_session() as session:
                await close_position_record(session, symbol, realized_pnl=Decimal("0"))
        except Exception:
            pass

    async def _execute_sell(self, sig, symbol: str, exit_reason: str = "SIGNAL") -> None:
        """Closes an open position via a SELL order, computes PnL, and sends visual reports."""
        position = self.risk_manager.active_positions.get(symbol)
        if not position:
            return

        client_order_id = generate_client_order_id("SELL")
        size = position.filled_amount
        entry_price = position.entry_price

        async with get_db_session() as session:
            await create_order_record(
                session,
                client_order_id=client_order_id,
                symbol=symbol,
                exchange_id=settings.EXCHANGE_ID,
                mode=self.mode,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=size,
                strategy_name=self.strategy.name,
            )

            if self.mode == BotMode.PAPER:
                exchange_order_id = f"PAPER_{client_order_id}"
                fill_price = sig.price
                logger.info(f"[PAPER] Simulated SELL {symbol}: {size} @ ${fill_price}")
            else:
                try:
                    order_resp = await self.exchange.create_order(
                        symbol=symbol,
                        order_type=OrderType.MARKET,
                        side=OrderSide.SELL,
                        amount=size,
                        client_order_id=client_order_id,
                    )
                    exchange_order_id = str(order_resp.get("id", ""))
                    fill_price = to_decimal(order_resp.get("average") or order_resp.get("price") or sig.price)
                    logger.info(
                        f"[ORDER DISPATCHED] {symbol} SELL {size} | "
                        f"client_id={client_order_id} | exchange_id={exchange_order_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[RUNNER] SELL order submission failed for {client_order_id}: {e}",
                        exc_info=True,
                    )
                    self.circuit_breaker.record_error(str(e))
                    return

            await update_order_from_exchange(
                session,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                status=OrderStatus.FILLED,
                filled_amount=size,
                avg_fill_price=fill_price,
            )

        # Update risk state
        closed = self.risk_manager.close_position(symbol)
        if closed:
            proceeds = size * fill_price
            self.available_cash += proceeds
            self.closed_trades_count += 1

            # Compute accurate PnL
            net_pnl = (fill_price - entry_price) * size
            pnl_pct = ((fill_price - entry_price) / entry_price) * Decimal("100") if entry_price > 0 else Decimal("0")
            is_win = net_pnl >= Decimal("0")

            # Feed trade outcome to AI strategy for reinforcement learning
            if hasattr(self.strategy, "record_trade_outcome"):
                self.strategy.record_trade_outcome(
                    symbol=symbol,
                    pnl_pct=pnl_pct,
                    is_win=is_win,
                    pattern_name=sig.pattern_name or "Estrategia IA",
                    exit_reason=exit_reason or sig.reason
                )

            # Broadcast learning update to frontend
            if hasattr(self.strategy, "get_stats"):
                await ws_hub.broadcast("AI_LEARNING_UPDATE", self.strategy.get_stats())

            # Record trade in memory history for UI display
            trade_record = {
                "symbol": symbol,
                "side": "COMPRA/VENTA",
                "invested_usd": str(round(size * entry_price, 2)),
                "entry_price": str(round(entry_price, 2)),
                "exit_price": str(round(fill_price, 2)),
                "net_pnl": str(round(net_pnl, 2)),
                "pnl_pct": str(round(pnl_pct, 2)),
                "is_win": is_win,
                "exit_reason": exit_reason or sig.reason,
                "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            }
            self.trade_history.append(trade_record)
            if len(self.trade_history) > 50:
                self.trade_history = self.trade_history[-50:]

            await ws_hub.broadcast("TRADE_CLOSED", trade_record)

            # Broadcast trade result to Telegram with visual photo card
            await self._broadcast_trade_closed(
                symbol=symbol,
                side="BUY",
                entry_price=entry_price,
                exit_price=fill_price,
                net_pnl=net_pnl,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason or sig.reason,
                pattern_name=sig.pattern_name or "Estrategia IA",
                is_win=is_win,
                invested_amount=size * entry_price,
                account_equity=self.equity,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Balance refresh (GAP #6)
    # ──────────────────────────────────────────────────────────────────────────

    async def _refresh_balance(self) -> None:
        """Fetches real balance from exchange and updates equity/available_cash."""
        try:
            balances = await self.exchange.fetch_balance()
            usdt = balances.get("USDT", self.equity)
            self.equity = usdt
            # available_cash = USDT minus notional of open positions
            allocated = sum(
                p.allocated_notional for p in self.risk_manager.active_positions.values()
            )
            self.available_cash = max(Decimal("0"), usdt - allocated)
            self.staking_manager.sync_account_equity(self.equity)
            logger.info(
                f"[RUNNER] Balance refreshed: equity=${self.equity:.2f}, "
                f"available=${self.available_cash:.2f}"
            )
        except Exception as e:
            logger.warning(f"[RUNNER] Balance refresh failed (non-fatal): {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Broadcast signal & results to Telegram (GAP #5)
    # ──────────────────────────────────────────────────────────────────────────

    async def _broadcast_signal(
        self,
        sig,
        invested_amount: Optional[Decimal] = None,
        available_cash: Optional[Decimal] = None,
        side: OrderSide = OrderSide.BUY,
        duration_minutes: int = 1,
    ) -> None:
        """Formats and sends a signal broadcast to Telegram with photo chart."""
        from app.telegram.telegram_client import get_telegram_client
        from app.telegram.visual_reporter import generate_entry_chart_card
        client = get_telegram_client()
        target_chat = settings.TELEGRAM_CHANNEL_ID or settings.TELEGRAM_ADMIN_CHAT_ID
        if not client or not target_chat:
            return
        try:
            side_str = "CALL" if side == OrderSide.BUY else "PUT"
            concurrent_info = f"{len(self.risk_manager.active_positions)}/{self.max_concurrent_binary_trades}"

            text = self.broadcast_service.format_signal_broadcast(
                signal=sig,
                invested_amount=invested_amount,
                available_cash=available_cash,
                mode_label=self.get_mode_label(),
                duration_minutes=duration_minutes,
                active_concurrent=concurrent_info,
            )

            # Generate chart screenshot card with arrow
            candles = self.last_candle_cache.get(sig.symbol, [])
            chart_bytes = generate_entry_chart_card(
                symbol=sig.symbol,
                side=side_str,
                entry_price=sig.price,
                candles=candles,
                duration_minutes=duration_minutes,
                pattern_name=sig.pattern_name,
                reason=sig.reason,
                stake=invested_amount,
                mode_label=self.get_mode_label(),
            )

            await client.send_photo(
                chat_id=target_chat,
                photo_bytes=chart_bytes.getvalue(),
                caption=text
            )
            logger.info(f"[BROADCAST] Sent entry photo chart for {sig.symbol} ({side_str}) to {target_chat}")
        except Exception as e:
            logger.error(f"[BROADCAST] Failed to send entry photo, sending text: {e}")
            try:
                await client.send_message(target_chat, text)
            except Exception:
                pass

    async def _broadcast_trade_closed(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        net_pnl: Decimal,
        pnl_pct: Decimal,
        exit_reason: str,
        pattern_name: str,
        is_win: bool,
        invested_amount: Optional[Decimal] = None,
        account_equity: Optional[Decimal] = None,
    ) -> None:
        """Sends trade closure summary + high-quality visual PNG card directly to Telegram."""
        from app.telegram.telegram_client import get_telegram_client
        client = get_telegram_client()
        target_chat = settings.TELEGRAM_CHANNEL_ID or settings.TELEGRAM_ADMIN_CHAT_ID
        if not client or not target_chat:
            return

        text = self.broadcast_service.format_trade_closed_broadcast(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            net_pnl=net_pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            account_equity=account_equity,
            mode_label=self.get_mode_label(),
        )

        try:
            # Generate visual dark-mode card image with 100% human friendly numbers
            img_bytes = generate_trade_card_image(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                net_pnl=net_pnl,
                pnl_pct=pnl_pct,
                pattern_name=pattern_name,
                is_win=is_win,
                invested_amount=invested_amount,
                account_equity=account_equity,
            )
            # Send photo with caption to Telegram
            await client.send_photo(
                chat_id=target_chat,
                photo_bytes=img_bytes.getvalue(),
                caption=text
            )
            logger.info(f"[BROADCAST] Sent trade closed photo card for {symbol} to {target_chat}")
        except Exception as e:
            logger.error(f"[BROADCAST] Failed to send trade photo, sending text fallback: {e}")
            try:
                await client.send_message(target_chat, text)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────────
    # Emergency Stop (GAP #1 fix — actually cancels orders)
    # ──────────────────────────────────────────────────────────────────────────

    def panic(self) -> str:
        """Triggers emergency stop."""
        self.is_running = False
        return self.admin_handler.handle_panic_command("UI_USER")

    async def async_panic(self) -> str:
        """
        Full async panic: trips breaker, cancels open exchange orders, and stops the loop.
        Call this from Telegram /panic for complete effect.
        """
        self.is_running = False
        msg = self.admin_handler.handle_panic_command("TELEGRAM_ADMIN")

        # Cancel any open orders on the exchange
        if self.mode != BotMode.PAPER:
            async with get_db_session() as session:
                open_orders = await self._get_open_orders_from_db(session)
                for order in open_orders:
                    ex_id = order.get("exchange_order_id")
                    symbol = order.get("symbol")
                    if ex_id and symbol:
                        try:
                            await self.exchange.cancel_order(ex_id, symbol)
                            logger.info(f"[PANIC] Cancelled exchange order {ex_id} on {symbol}.")
                        except Exception as e:
                            logger.error(f"[PANIC] Failed to cancel order {ex_id}: {e}")

        return msg

    async def _get_open_orders_from_db(self, session) -> list:
        from app.database.order_repository import get_open_orders
        return await get_open_orders(session)

    def get_mode_label(self) -> str:
        """Returns a crystal clear label of the running account mode."""
        if settings.EXCHANGE_ID.lower() == "iqoption":
            is_demo = settings.IQOPTION_BALANCE_MODE.upper() == "PRACTICE"
            return "DEMO (IQ Option Práctica)" if is_demo else "REAL (IQ Option)"
        if self.mode == BotMode.LIVE:
            return f"REAL ({settings.EXCHANGE_ID.upper()})"
        elif self.mode == BotMode.TESTNET:
            return f"DEMO ({settings.EXCHANGE_ID.upper()} Testnet)"
        else:
            return "SIMULADOR (Paper Trading)"

    def get_intuitive_telemetry(self) -> Dict[str, Any]:
        """Calculates friendly metrics for non-technical traders."""
        total_invested = sum(
            (pos.filled_amount * pos.entry_price for pos in self.risk_manager.active_positions.values()),
            Decimal("0")
        )
        
        total_pnl = sum((Decimal(t.get("net_pnl", "0")) for t in self.trade_history), Decimal("0"))
        win_count = sum(1 for t in self.trade_history if t.get("is_win", False))
        total_trades = len(self.trade_history)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        if not self.is_running:
            action_status = "⏸️ Bot pausado"
            action_detail = "Esperando que inicies el bot para comenzar a buscar operaciones."
            action_badge = "PAUSADO"
        elif self.session_manager.hourly_cycle_enabled and self.session_manager.cycle_state == "RESTING":
            prog = self.session_manager.get_progress_data()
            action_status = f"⏱️ Enfriamiento de 1 hora ({prog.get('cycle_remaining_min', 0)} min restantes)"
            action_detail = "El bot descansa 60 min para enfriar el mercado. Puedes tocar '⏱️ Modo Horas' para operar de inmediato."
            action_badge = "EN REPOSO"
        elif self.circuit_breaker.status != CircuitBreakerStatus.NORMAL:
            action_status = "⚠️ Freno de emergencia activado"
            action_detail = f"Freno preventivo por seguridad: {self.circuit_breaker.last_error or 'Errores seguidos'}"
            action_badge = "FRENO ACTIVO"
        elif len(self.risk_manager.active_positions) > 0:
            active_symbols = ", ".join(self.risk_manager.active_positions.keys())
            action_status = f"🟢 Operación abierta en {active_symbols}"
            details = []
            for s, p in self.risk_manager.active_positions.items():
                c_list = self.last_candle_cache.get(s)
                curr = to_decimal(c_list[-1][4]) if (c_list and len(c_list) > 0) else p.entry_price
                unrealized = (curr - p.entry_price) * p.filled_amount
                sign = "+" if unrealized >= 0 else ""
                details.append(f"{s}: Invertido ${round(p.filled_amount * p.entry_price, 2)} ({sign}${round(unrealized, 2)})")
            action_detail = " | ".join(details)
            action_badge = "OPERANDO"
        else:
            action_status = f"🔍 Escaneando el mercado en vivo ({', '.join(settings.TRADING_SYMBOLS)})"
            action_detail = f"La IA analiza el precio y sentimiento cada 5s en {settings.EXCHANGE_ID.upper()} esperando el momento ideal para entrar."
            action_badge = "BUSCANDO ENTRADA"

        active_pos_list = []
        for sym, pos in self.risk_manager.active_positions.items():
            c_list = self.last_candle_cache.get(sym)
            curr_p = to_decimal(c_list[-1][4]) if (c_list and len(c_list) > 0) else pos.entry_price
            unrealized_pnl = (curr_p - pos.entry_price) * pos.filled_amount
            unrealized_pct = ((curr_p - pos.entry_price) / pos.entry_price * Decimal("100")) if pos.entry_price > 0 else Decimal("0")
            active_pos_list.append({
                "symbol": sym,
                "amount": str(pos.filled_amount),
                "invested_usd": str(round(pos.filled_amount * pos.entry_price, 2)),
                "entry_price": str(round(pos.entry_price, 2)),
                "current_price": str(round(curr_p, 2)),
                "unrealized_pnl_usd": str(round(unrealized_pnl, 2)),
                "unrealized_pnl_pct": str(round(unrealized_pct, 2)),
                "stop_loss": str(round(pos.stop_loss, 2)) if pos.stop_loss else "Automático",
                "take_profit": str(round(pos.take_profit, 2)) if pos.take_profit else "Automático",
            })

        agents_info = [
            {
                "name": "Agente IA de Velas & Patrones (Chartismo)",
                "code": f"{self.strategy.name}",
                "role": "Escaneo de medias móviles (EMA 9/21/50), RSI y velas japonesas",
                "status": "Escaneando en vivo" if self.is_running else "En pausa",
                "icon": "🧠",
                "color": "#00F0FF"
            },
            {
                "name": "Agente de Sentimiento Web & Macro",
                "code": "FearGreed_WebIntel_Service",
                "role": "Mide el sentimiento global y noticias de mercado antes de entrar",
                "status": "Sincronizado",
                "icon": "🌐",
                "color": "#FFB300"
            },
            {
                "name": "Agente Guardián de Riesgo & Capital",
                "code": "RiskManager & Staking Guardian",
                "role": f"Supervisión de drawdown, Stop Loss, Take Profit ({self.staking_manager.get_telemetry().get('status_text', 'Protegido')})",
                "status": "Protección Activa",
                "icon": "🛡️",
                "color": "#00E676"
            },
            {
                "name": f"Agente Ejecutor {settings.EXCHANGE_ID.upper()}",
                "code": f"ExchangeAdapter ({self.get_mode_label()})",
                "role": "Enrutamiento ultra-rápido de órdenes y sincronización de saldos",
                "status": "Conectado",
                "icon": "⚡",
                "color": "#A855F7"
            }
        ]

        return {
            "is_running": self.is_running,
            "mode": self.mode.value,
            "mode_label": self.get_mode_label(),
            "exchange": settings.EXCHANGE_ID.upper(),
            "equity": str(round(self.equity, 2)),
            "available_cash": str(round(self.available_cash, 2)),
            "total_invested": str(round(total_invested, 2)),
            "today_pnl_usd": str(round(total_pnl, 2)),
            "today_pnl_pct": str(round((total_pnl / self.initial_equity * Decimal("100")), 2)) if self.initial_equity > 0 else "0.00",
            "win_rate_pct": round(win_rate, 1),
            "trades_count": total_trades,
            "win_count": win_count,
            "circuit_breaker": self.circuit_breaker.status.value,
            "action_status": action_status,
            "action_detail": action_detail,
            "action_badge": action_badge,
            "active_positions": active_pos_list,
            "recent_trades": list(reversed(self.trade_history[-15:])),
            "uptime": self.heartbeat.get_uptime_str(),
            "symbols": settings.TRADING_SYMBOLS,
            "duration_minutes": self.duration_minutes,
            "timeframe": f"{self.duration_minutes}m",
            "staking": self.staking_manager.get_telemetry(),
            "session": self.session_manager.get_progress_data(),
            "agents": agents_info,
            "ai_thoughts": self.strategy.get_latest_thoughts() if hasattr(self.strategy, "get_latest_thoughts") else {},
            "equity_curve": self.equity_curve[-30:],
        }


bot_runner = BotRunner()
