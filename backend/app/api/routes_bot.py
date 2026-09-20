"""FastAPI REST Endpoints for Bot Control and Monitoring."""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.constants import BotMode
from app.core.logger import logger
from app.engine.bot_runner import bot_runner
from app.engine.backtester import BacktestingEngine
from app.strategies.example_strategy import TrendMomentumStrategy
from app.api.websocket_hub import ws_hub

router = APIRouter(prefix="/api/bot", tags=["Bot Controller"])


class StakingConfigRequest(BaseModel):
    base_stake: Optional[float] = None
    steps: Optional[List[float]] = None



class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    initial_capital: float = 10000.0
    fast_period: int = 9
    slow_period: int = 21


class ResumeRequest(BaseModel):
    operator_id: str = "admin"
    justification: str


@router.get("/status")
async def get_status():
    """Returns current intuitive runtime telemetry and risk status."""
    try:
        return bot_runner.get_intuitive_telemetry()
    except Exception as e:
        logger.error(f"[ROUTE] /status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles")
async def get_candles(symbol: str = "BTC/USDT"):
    """Returns real candlestick data fetched from Binance/exchange."""
    candles = bot_runner.last_candle_cache.get(symbol, [])
    if not candles and bot_runner.exchange.is_initialized:
        try:
            candles = await bot_runner.exchange.fetch_ohlcv(symbol, timeframe=settings.DEFAULT_TIMEFRAME, limit=100)
            bot_runner.last_candle_cache[symbol] = candles
        except Exception:
            pass

    # Format for TradingView Lightweight Charts: [{ time, open, high, low, close }]
    formatted = []
    for c in candles:
        # ccxt ohlcv: [timestamp_ms, open, high, low, close, volume]
        t = int(c[0] / 1000) if c[0] > 1e11 else int(c[0])
        formatted.append({
            "time": t,
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
        })
    return {"symbol": symbol, "candles": formatted}


@router.get("/ai-stats")
async def get_ai_stats():
    """Returns real-time AI strategy learning statistics and learned pattern weights."""
    if hasattr(bot_runner.strategy, "get_stats"):
        return bot_runner.strategy.get_stats()
    return {"status": "Strategy does not expose stats"}


@router.post("/start")
async def start_bot():
    """Starts the trading loop and resets resting/target locks."""
    bot_runner.reset_and_resume_trading()

    if not bot_runner.exchange.is_initialized:
        result = await bot_runner.start()
        return {
            "success": bot_runner.is_running,
            "is_clean": result.is_clean,
            "message": result.summary_message
        }
    else:
        await ws_hub.broadcast("STATUS_UPDATE", bot_runner.get_intuitive_telemetry())
        return {
            "success": True,
            "is_clean": True,
            "message": "Bot iniciado y buscando operaciones activamente."
        }


@router.post("/stop")
async def stop_bot():
    """Stops scanning without emergency close."""
    bot_runner.is_running = False
    return {"success": True, "message": "Trading bot paused safely."}


@router.post("/panic")
async def panic_stop():
    """Emergency Panic Stop."""
    msg = bot_runner.panic()
    return {"success": True, "message": msg}


@router.post("/staking")
async def update_staking(req: StakingConfigRequest):
    """Updates Martingale progression steps (e.g. $1 -> $2 -> $4)."""
    if req.steps:
        updated = bot_runner.staking_manager.set_steps(req.steps)
    elif req.base_stake is not None:
        updated = bot_runner.staking_manager.set_base_stake(req.base_stake)
    else:
        raise HTTPException(status_code=400, detail="Must provide base_stake or steps")

    await ws_hub.broadcast("STATUS_UPDATE", bot_runner.get_intuitive_telemetry())
    return {
        "success": True,
        "steps": updated,
        "current_stake": float(bot_runner.staking_manager.get_current_stake()),
        "message": f"Martingala actualizada: {' → '.join(f'${s:.0f}' for s in updated)} USD"
    }


@router.get("/staking")
async def get_staking():
    """Returns current staking telemetry."""
    return bot_runner.staking_manager.get_telemetry()


@router.get("/session")
@router.get("/target")
async def get_session_target():
    """Returns session progress, target mode and marathon goal telemetry."""
    return bot_runner.session_manager.get_progress_data()



@router.post("/force-trade")
async def force_trade(symbol: str = "EURUSD-OTC", direction: str = "BUY", duration_minutes: Optional[int] = None):
    """Forces an immediate test trade on the exchange to demonstrate execution."""
    from app.strategies.base_strategy import StrategySignal
    from app.core.constants import OrderSide, SignalType
    from app.core.decimal_math import to_decimal
    
    if not bot_runner.exchange.is_initialized:
        await bot_runner.start()
        
    if duration_minutes:
        bot_runner.set_timeframe(f"{duration_minutes}m")

    sig_type = SignalType.BUY if direction.upper() in ("BUY", "CALL") else SignalType.SELL
    order_side = OrderSide.BUY if sig_type == SignalType.BUY else OrderSide.SELL
    candles = await bot_runner.exchange.fetch_ohlcv(symbol, limit=5)
    last_p = to_decimal(candles[-1][4]) if candles else Decimal("1.1400")
    
    dur_str = f"{bot_runner.duration_minutes} Minuto" if bot_runner.duration_minutes == 1 else f"{bot_runner.duration_minutes} Minutos"
    dir_label = "CALL (Subida 🟢)" if order_side == OrderSide.BUY else "PUT (Bajada 🔴)"
    sig = StrategySignal(
        symbol=symbol,
        signal_type=sig_type,
        price=last_p,
        pattern_name=f"Operación Manual ({dir_label} - {dur_str}) ⚡",
        reason=f"Demostración en vivo ejecutada desde el panel web ({dur_str}) con captura gráfica"
    )
    
    await bot_runner._execute_buy(sig, symbol, side=order_side)
        
    return {
        "success": True,
        "message": f"¡Orden {direction.upper()} ({dur_str}) enviada con éxito a IQ Option en {symbol}! Mira tu pantalla de IQ Option."
    }


@router.post("/timeframe")
async def set_timeframe(timeframe: str = Query("1m", description="Expiration duration: 1m, 2m, 3m, 5m")):
    """Configures expiration timeframe for binary options."""
    mins = bot_runner.set_timeframe(timeframe)
    dur_label = f"{mins} Minuto" if mins == 1 else f"{mins} Minutos"
    return {
        "success": True,
        "timeframe": f"{mins}m",
        "duration_minutes": mins,
        "message": f"Duración de expiración ajustada a {dur_label}."
    }


@router.get("/equity-history")
async def get_equity_history():
    """Returns equity curve points for live performance chart."""
    return {
        "equity_curve": bot_runner.equity_curve,
        "current_equity": float(bot_runner.equity),
        "initial_equity": float(bot_runner.initial_equity),
    }


@router.post("/resume-after-review")
async def resume_after_review(payload: ResumeRequest):
    """Explicitly resumes after manual review of discrepancies."""
    res = bot_runner.admin_handler.handle_resume_after_review(
        user_id=payload.operator_id,
        reason=payload.justification
    )
    return {"success": not bot_runner.reconciler.is_locked_for_review, "message": res}


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """Executes walk-forward backtest on historical or synthetic dataset."""
    strategy = TrendMomentumStrategy(
        symbols=[req.symbol],
        params={"fast_period": req.fast_period, "slow_period": req.slow_period}
    )
    engine = BacktestingEngine(initial_capital=Decimal(str(req.initial_capital)))

    # Use cached candles or generate series
    candles = bot_runner.last_candle_cache.get(req.symbol)
    if not candles or len(candles) < 30:
        # Fetch or generate test candles
        candles = await bot_runner.exchange.fetch_ohlcv(req.symbol, limit=100) if bot_runner.exchange.is_initialized else []

    if not candles:
        from app.utils.synthetic_data import generate_synthetic_ohlcv_trend
        candles = generate_synthetic_ohlcv_trend(n_bars=150)

    wf_result = engine.run_walk_forward_backtest(strategy, candles, req.symbol)
    
    return {
        "symbol": req.symbol,
        "initial_capital": str(req.initial_capital),
        "in_sample": {
            "net_profit_pct": str(wf_result.in_sample_report.net_profit_pct),
            "win_rate_pct": str(wf_result.in_sample_report.win_rate_pct),
            "max_drawdown_pct": str(wf_result.in_sample_report.max_drawdown_pct),
            "trades_count": wf_result.in_sample_report.total_trades
        },
        "out_of_sample": {
            "net_profit_pct": str(wf_result.out_of_sample_report.net_profit_pct),
            "win_rate_pct": str(wf_result.out_of_sample_report.win_rate_pct),
            "max_drawdown_pct": str(wf_result.out_of_sample_report.max_drawdown_pct),
            "trades_count": wf_result.out_of_sample_report.total_trades
        },
        "full_period": {
            "net_profit_pct": str(wf_result.full_report.net_profit_pct),
            "final_balance": str(wf_result.full_report.final_balance),
            "max_drawdown_pct": str(wf_result.full_report.max_drawdown_pct),
            "total_fees_paid": str(wf_result.full_report.total_fees_paid),
            "profit_factor": str(wf_result.full_report.profit_factor),
            "total_trades": wf_result.full_report.total_trades
        },
        "overfitting_diagnosis": wf_result.overfitting_warning
    }
