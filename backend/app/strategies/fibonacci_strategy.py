"""Estrategia Cuantitativa de Retrocesos y Confluencia de Fibonacci.

Diseñada especialmente para operaciones de alta probabilidad en Opciones Binarias y Forex (1m - 5m).
Fundamentada en las proporciones áureas de Fibonacci (Golden Ratio):
  - 0.236, 0.382 (Retrocesos superficiales de continuación veloz)
  - 0.500 (Nivel institucional psicológico de equilibrio)
  - 0.618 (Golden Pocket - Proporción Áurea de máxima reversión institucional)
  - 0.786 (Deep Retracement - Raíz de 0.618, última defensa de tendencia)

Reglas de Entrada Cuantitativas:
  1. Identificación Algorítmica de Estructura de Mercado:
     - Detección de Swing High y Swing Low locales mediante fractales y picos.
     - Filtro Macro Trend: EMA 50 y EMA 150 para garantizar que solo operamos a favor de la tendencia.
  2. Mapeo Dinámico de la Cuadrícula Fibonacci:
     - Cálculo de la amplitud del impulso (Rango = High - Low).
     - Validación de amplitud mínima para filtrar periodos muertos o sin volatilidad.
  3. Detección del Retroceso en la Zona Dorada (50% - 61.8% - 78.6%):
     - Monitoreo en tiempo real del retesteo del nivel clave.
  4. Gatillo de Acción del Precio (Price Action Confluence):
     - Mecha de rechazo (Rejection Wick / Pinbar / Hammer) sobre el nivel Fibonacci.
     - Confluencia de giro de momentum (RSI curvándose desde la zona de retroceso).
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import math

from app.core.constants import SignalType
from app.core.decimal_math import to_decimal
from app.core.logger import logger
from app.strategies.base_strategy import BaseStrategy, StrategySignal


class FibonacciRetracementStrategy(BaseStrategy):
    """
    Estrategia Cuantitativa basada en Retrocesos de Fibonacci y Acción del Precio.
    """

    FIB_LEVELS = {
        "FIB_236": Decimal("0.236"),
        "FIB_382": Decimal("0.382"),
        "FIB_500": Decimal("0.500"),
        "FIB_618": Decimal("0.618"),  # Golden Ratio
        "FIB_786": Decimal("0.786"),  # Deep Golden Pocket
    }

    def __init__(self, symbols: List[str], timeframe: str = "1m", params: Optional[Dict[str, Any]] = None):
        default_params = {
            "swing_window": 35,           # Cantidad de velas para detectar Swing High y Swing Low
            "min_impulse_pct": Decimal("0.03"),  # Amplitud mínima del impulso (% del precio, ~3 pips)
            "tolerance_pct": Decimal("0.06"),    # Tolerancia de proximidad al nivel Fib (en %)
            "trend_ema": 30,              # EMA intermedia para dirección de tendencia
            "macro_ema": 100,             # EMA macro institucional
            "rsi_period": 14,             # Periodo de RSI para confluencia
            "min_confidence": Decimal("0.70"), # Umbral de confianza mínimo para disparar señal
            "rejection_wick_ratio": Decimal("0.8"), # Ratio de mecha respecto al cuerpo para validar rechazo
        }
        if params:
            default_params.update(params)

        super().__init__(
            name="Fibonacci_GoldenPocket_v1",
            symbols=symbols,
            timeframe=timeframe,
            params=default_params
        )

        self.latest_thoughts: Dict[str, str] = {}
        self.stats_by_level: Dict[str, Dict[str, Any]] = {
            "FIB_382": {"wins": 0, "losses": 0, "total": 0, "win_rate": 0.0},
            "FIB_500": {"wins": 0, "losses": 0, "total": 0, "win_rate": 0.0},
            "FIB_618": {"wins": 0, "losses": 0, "total": 0, "win_rate": 0.0},
            "FIB_786": {"wins": 0, "losses": 0, "total": 0, "win_rate": 0.0},
        }
        self.total_signals_generated = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Métodos Matemáticos de Indicadores
    # ──────────────────────────────────────────────────────────────────────────

    def _calc_ema(self, values: List[Decimal], period: int) -> Decimal:
        """Calcula Media Móvil Exponencial (EMA) con suavizado alpha."""
        if not values or len(values) < period:
            return values[-1] if values else Decimal("0")

        alpha = Decimal(str(2.0 / (period + 1)))
        ema = values[0]
        for val in values[1:]:
            ema = (val * alpha) + (ema * (Decimal("1") - alpha))
        return ema

    def _calc_rsi(self, closes: List[Decimal], period: int = 14) -> Decimal:
        """Calcula el Relative Strength Index (RSI)."""
        if len(closes) <= period:
            return Decimal("50.0")

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff >= Decimal("0"):
                gains.append(diff)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(abs(diff))

        if len(gains) < period:
            return Decimal("50.0")

        avg_gain = sum(gains[:period]) / Decimal(str(period))
        avg_loss = sum(losses[:period]) / Decimal(str(period))

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * Decimal(str(period - 1)) + gains[i]) / Decimal(str(period))
            avg_loss = (avg_loss * Decimal(str(period - 1)) + losses[i]) / Decimal(str(period))

        if avg_loss == Decimal("0"):
            return Decimal("100.0")
        rs = avg_gain / avg_loss
        rsi = Decimal("100.0") - (Decimal("100.0") / (Decimal("1.0") + rs))
        return rsi

    def _find_swings(
        self, highs: List[Decimal], lows: List[Decimal], window: int
    ) -> Tuple[Decimal, int, Decimal, int]:
        """
        Encuentra el Swing High y Swing Low y sus índices relativos en la ventana de velas.
        Retorna (swing_high, idx_high, swing_low, idx_low).
        """
        sub_highs = highs[-window:]
        sub_lows = lows[-window:]

        swing_high = max(sub_highs)
        idx_high = sub_highs.index(swing_high)

        swing_low = min(sub_lows)
        idx_low = sub_lows.index(swing_low)

        return swing_high, idx_high, swing_low, idx_low

    def _calculate_fib_levels(
        self, swing_high: Decimal, swing_low: Decimal, trend: str
    ) -> Dict[str, Decimal]:
        """
        Calcula los niveles de precio correspondientes a cada ratio de Fibonacci.
        - En tendencia ALCISTA (Impulso alcista: Low -> High, esperando retroceso abajo):
            Nivel(k) = High - (High - Low) * k
        - En tendencia BAJISTA (Impulso bajista: High -> Low, esperando retroceso arriba):
            Nivel(k) = Low + (High - Low) * k
        """
        diff = swing_high - swing_low
        levels = {}

        if trend == "BULLISH":
            for name, ratio in self.FIB_LEVELS.items():
                levels[name] = swing_high - (diff * ratio)
        else:  # BEARISH
            for name, ratio in self.FIB_LEVELS.items():
                levels[name] = swing_low + (diff * ratio)

        return levels

    # ──────────────────────────────────────────────────────────────────────────
    # Generación de Señales de Trading
    # ──────────────────────────────────────────────────────────────────────────

    def generate_signals(
        self, market_data: Dict[str, Any], open_positions: Dict[str, Any]
    ) -> List[StrategySignal]:
        """
        Evalúa el flujo de velas en vivo buscando retrocesos y rechazos en niveles áureos de Fibonacci.
        """
        signals: List[StrategySignal] = []
        window = int(self.params["swing_window"])
        min_candles = max(window, int(self.params.get("trend_ema", 50))) + 2

        for symbol in self.symbols:
            if symbol not in market_data:
                continue
            candles = market_data.get(symbol, [])
            if len(candles) < min_candles:
                self.latest_thoughts[symbol] = (
                    f"⏳ Recopilando velas para {symbol} ({len(candles)}/{min_candles})..."
                )
                continue

            # Extracción y tipado de OHLCV
            opens = [to_decimal(c[1]) for c in candles]
            highs = [to_decimal(c[2]) for c in candles]
            lows = [to_decimal(c[3]) for c in candles]
            closes = [to_decimal(c[4]) for c in candles]

            curr_open = opens[-1]
            curr_high = highs[-1]
            curr_low = lows[-1]
            curr_close = closes[-1]
            curr_price = curr_close

            prev_open = opens[-2]
            prev_high = highs[-2]
            prev_low = lows[-2]
            prev_close = closes[-2]

            # Indicadores de Tendencia y Momentum
            trend_ema = self._calc_ema(closes, self.params["trend_ema"])
            macro_ema = self._calc_ema(closes, self.params["macro_ema"])
            rsi = self._calc_rsi(closes, self.params["rsi_period"])
            prev_rsi = self._calc_rsi(closes[:-1], self.params["rsi_period"])

            # 1. Detección de Swings
            sw_high, idx_high, sw_low, idx_low = self._find_swings(highs, lows, window)
            impulse_range = sw_high - sw_low

            if sw_low <= Decimal("0"):
                continue

            impulse_pct = (impulse_range / sw_low) * Decimal("100.0")
            min_impulse = to_decimal(self.params["min_impulse_pct"])

            # Si el rango es demasiado estrecho, el mercado está en rango plano/muerto
            if impulse_pct < min_impulse:
                self.latest_thoughts[symbol] = (
                    f"⚠️ Rango plano en {symbol} ({impulse_pct:.3f}% < {min_impulse}%). Esperando impulso claro."
                )
                continue

            # Determinación de dirección del impulso y estructura
            # Tendencia Alcista: El Low ocurrió antes del High (idx_low < idx_high) y precio sobre EMA
            is_bullish_impulse = (idx_low < idx_high) and (curr_price >= trend_ema * Decimal("0.998"))
            # Tendencia Bajista: El High ocurrió antes del Low (idx_high < idx_low) y precio bajo EMA
            is_bearish_impulse = (idx_high < idx_low) and (curr_price <= trend_ema * Decimal("1.002"))

            tolerance_pct = to_decimal(self.params["tolerance_pct"]) / Decimal("100.0")

            # ──────────────────────────────────────────────────────────────────
            # ESCENARIO 1: RETROCESO FIBONACCI ALCISTA (CALL / BUY)
            # ──────────────────────────────────────────────────────────────────
            if is_bullish_impulse:
                fib_levels = self._calculate_fib_levels(sw_high, sw_low, trend="BULLISH")
                matched_level_name = None
                matched_level_price = None

                # Evaluar niveles objetivo: 50%, 61.8% (Golden), 78.6% (Deep), 38.2%
                target_levels = ["FIB_618", "FIB_500", "FIB_786", "FIB_382"]
                for lvl_name in target_levels:
                    lvl_price = fib_levels[lvl_name]
                    dist_pct = abs(curr_price - lvl_price) / lvl_price
                    # Verificamos si el precio actual o el mínimo de la vela tocó el nivel dentro de tolerancia
                    if dist_pct <= tolerance_pct or (curr_low <= lvl_price <= curr_high):
                        matched_level_name = lvl_name
                        matched_level_price = lvl_price
                        break

                if matched_level_name:
                    # Análisis de Rechazo / Acción del Precio (Rejection Wick / Hammer)
                    candle_range = curr_high - curr_low
                    body = abs(curr_close - curr_open)
                    lower_wick = min(curr_open, curr_close) - curr_low

                    is_bullish_rejection = False
                    wick_ratio = lower_wick / (body if body > Decimal("0") else Decimal("0.00001"))

                    # Rechazo: Mecha inferior larga sobre el soporte Fibonacci o vela verde de rebote
                    if wick_ratio >= to_decimal(self.params["rejection_wick_ratio"]):
                        is_bullish_rejection = True
                    elif curr_close > curr_open and prev_close <= matched_level_price:
                        # Rebote de confirmación (vela verde saliendo del soporte)
                        is_bullish_rejection = True

                    # Confluencia de RSI (no sobrecomprado, girando hacia arriba)
                    rsi_rebound = (rsi < Decimal("60.0")) and (rsi >= prev_rsi)

                    # Ponderación de confianza matemática
                    base_conf = Decimal("0.70")
                    if matched_level_name == "FIB_618":
                        base_conf += Decimal("0.12")  # Golden Ratio da máxima confianza
                    elif matched_level_name == "FIB_500":
                        base_conf += Decimal("0.08")  # Equilibrio institucional 50%
                    elif matched_level_name == "FIB_786":
                        base_conf += Decimal("0.10")  # Deep bounce
                    else:
                        base_conf += Decimal("0.05")

                    if curr_price > trend_ema:
                        base_conf += Decimal("0.05")
                    if rsi_rebound:
                        base_conf += Decimal("0.05")
                    if wick_ratio >= Decimal("2.0"):
                        base_conf += Decimal("0.05")

                    confidence = min(Decimal("0.95"), base_conf)

                    self.latest_thoughts[symbol] = (
                        f"🎯 FIB ALCISTA en {symbol}: Nivel {matched_level_name} ({matched_level_price:.5f}) "
                        f"testeado. Dist: {abs(curr_price - matched_level_price):.5f} | Mecha/Cuerpo: {wick_ratio:.1f}x | "
                        f"RSI: {rsi:.1f} | Conf: {int(confidence*100)}%"
                    )

                    if is_bullish_rejection and confidence >= to_decimal(self.params["min_confidence"]):
                        sl_price = sw_low * Decimal("0.999")  # SL bajo el swing low
                        tp_price = sw_high * Decimal("1.001")  # TP hacia el swing high previo

                        sig = StrategySignal(
                            symbol=symbol,
                            signal_type=SignalType.BUY,
                            price=curr_price,
                            stop_loss=sl_price,
                            take_profit=tp_price,
                            confidence=confidence,
                            pattern_name=f"FIB_CALL_{matched_level_name}",
                            reason=(
                                f"Rebote en soporte áureo Fibonacci {matched_level_name} (${matched_level_price:.5f}) "
                                f"con mecha de rechazo {wick_ratio:.1f}x y RSI {rsi:.1f} en tendencia alcista."
                            ),
                            metadata={
                                "fib_level": matched_level_name,
                                "level_price": float(matched_level_price),
                                "swing_high": float(sw_high),
                                "swing_low": float(sw_low),
                                "wick_ratio": float(wick_ratio),
                                "confidence": float(confidence),
                            }
                        )
                        signals.append(sig)
                        self.total_signals_generated += 1
                        logger.info(
                            f"[FIBONACCI] ✨ Señal CALL generada en {symbol} @ {curr_price} "
                            f"(Nivel: {matched_level_name}, Conf: {int(confidence*100)}%)"
                        )
                else:
                    # En seguimiento de retroceso
                    fib_618 = fib_levels["FIB_618"]
                    dist_to_gold = ((curr_price - fib_618) / fib_618) * Decimal("100.0")
                    self.latest_thoughts[symbol] = (
                        f"📐 Monitor Alcista {symbol}: Swing L:{sw_low:.5f} -> H:{sw_high:.5f}. "
                        f"Golden 61.8% en {fib_618:.5f}. Precio a {dist_to_gold:+.2f}% del nivel."
                    )

            # ──────────────────────────────────────────────────────────────────
            # ESCENARIO 2: RETROCESO FIBONACCI BAJISTA (PUT / SELL)
            # ──────────────────────────────────────────────────────────────────
            elif is_bearish_impulse:
                fib_levels = self._calculate_fib_levels(sw_high, sw_low, trend="BEARISH")
                matched_level_name = None
                matched_level_price = None

                target_levels = ["FIB_618", "FIB_500", "FIB_786", "FIB_382"]
                for lvl_name in target_levels:
                    lvl_price = fib_levels[lvl_name]
                    dist_pct = abs(curr_price - lvl_price) / lvl_price
                    if dist_pct <= tolerance_pct or (curr_low <= lvl_price <= curr_high):
                        matched_level_name = lvl_name
                        matched_level_price = lvl_price
                        break

                if matched_level_name:
                    # Análisis de Rechazo / Acción del Precio (Shooting Star / Mecha superior)
                    candle_range = curr_high - curr_low
                    body = abs(curr_close - curr_open)
                    upper_wick = curr_high - max(curr_open, curr_close)

                    is_bearish_rejection = False
                    wick_ratio = upper_wick / (body if body > Decimal("0") else Decimal("0.00001"))

                    if wick_ratio >= to_decimal(self.params["rejection_wick_ratio"]):
                        is_bearish_rejection = True
                    elif curr_close < curr_open and prev_close >= matched_level_price:
                        # Vela roja saliendo de la resistencia
                        is_bearish_rejection = True

                    # Confluencia de RSI (no sobrevendido, girando hacia abajo)
                    rsi_rebound = (rsi > Decimal("40.0")) and (rsi <= prev_rsi)

                    base_conf = Decimal("0.70")
                    if matched_level_name == "FIB_618":
                        base_conf += Decimal("0.12")
                    elif matched_level_name == "FIB_500":
                        base_conf += Decimal("0.08")
                    elif matched_level_name == "FIB_786":
                        base_conf += Decimal("0.10")
                    else:
                        base_conf += Decimal("0.05")

                    if curr_price < trend_ema:
                        base_conf += Decimal("0.05")
                    if rsi_rebound:
                        base_conf += Decimal("0.05")
                    if wick_ratio >= Decimal("2.0"):
                        base_conf += Decimal("0.05")

                    confidence = min(Decimal("0.95"), base_conf)

                    self.latest_thoughts[symbol] = (
                        f"🎯 FIB BAJISTA en {symbol}: Nivel {matched_level_name} ({matched_level_price:.5f}) "
                        f"testeado. Dist: {abs(curr_price - matched_level_price):.5f} | Mecha/Cuerpo: {wick_ratio:.1f}x | "
                        f"RSI: {rsi:.1f} | Conf: {int(confidence*100)}%"
                    )

                    if is_bearish_rejection and confidence >= to_decimal(self.params["min_confidence"]):
                        sl_price = sw_high * Decimal("1.001")
                        tp_price = sw_low * Decimal("0.999")

                        sig = StrategySignal(
                            symbol=symbol,
                            signal_type=SignalType.SELL,
                            price=curr_price,
                            stop_loss=sl_price,
                            take_profit=tp_price,
                            confidence=confidence,
                            pattern_name=f"FIB_PUT_{matched_level_name}",
                            reason=(
                                f"Rechazo en resistencia áurea Fibonacci {matched_level_name} (${matched_level_price:.5f}) "
                                f"con mecha superior {wick_ratio:.1f}x y RSI {rsi:.1f} en tendencia bajista."
                            ),
                            metadata={
                                "fib_level": matched_level_name,
                                "level_price": float(matched_level_price),
                                "swing_high": float(sw_high),
                                "swing_low": float(sw_low),
                                "wick_ratio": float(wick_ratio),
                                "confidence": float(confidence),
                            }
                        )
                        signals.append(sig)
                        self.total_signals_generated += 1
                        logger.info(
                            f"[FIBONACCI] ✨ Señal PUT generada en {symbol} @ {curr_price} "
                            f"(Nivel: {matched_level_name}, Conf: {int(confidence*100)}%)"
                        )
                else:
                    fib_618 = fib_levels["FIB_618"]
                    dist_to_gold = ((fib_618 - curr_price) / fib_618) * Decimal("100.0")
                    self.latest_thoughts[symbol] = (
                        f"📐 Monitor Bajista {symbol}: Swing H:{sw_high:.5f} -> L:{sw_low:.5f}. "
                        f"Golden 61.8% en {fib_618:.5f}. Precio a {dist_to_gold:+.2f}% del nivel."
                    )
            else:
                self.latest_thoughts[symbol] = (
                    f"🔍 Escaneando {symbol}: Estructura lateral o transición. Esperando nuevo fractal/swing."
                )

        return signals

    # ──────────────────────────────────────────────────────────────────────────
    # Telemetría y Feedback Loop
    # ──────────────────────────────────────────────────────────────────────────

    def record_trade_outcome(
        self,
        symbol: str,
        pnl_pct: Decimal,
        is_win: bool,
        pattern_name: str,
        exit_reason: str = ""
    ) -> None:
        """Registra el resultado de las operaciones por nivel de Fibonacci."""
        for lvl in self.stats_by_level.keys():
            if lvl in pattern_name:
                stat = self.stats_by_level[lvl]
                stat["total"] += 1
                if is_win:
                    stat["wins"] += 1
                else:
                    stat["losses"] += 1
                stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1)
                break

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas cuantitativas de la estrategia Fibonacci."""
        total_trades = sum(s["total"] for s in self.stats_by_level.values())
        total_wins = sum(s["wins"] for s in self.stats_by_level.values())
        overall_wr = round((total_wins / total_trades) * 100, 1) if total_trades > 0 else 0.0

        return {
            "name": self.name,
            "strategy_type": "Fibonacci Retracement & Golden Pocket Confluence",
            "total_signals_generated": self.total_signals_generated,
            "total_trades_completed": total_trades,
            "overall_win_rate": overall_wr,
            "stats_by_level": self.stats_by_level,
            "monitored_symbols": self.symbols,
            "parameters": {
                "swing_window": self.params["swing_window"],
                "min_impulse_pct": float(self.params["min_impulse_pct"]),
                "tolerance_pct": float(self.params["tolerance_pct"]),
                "min_confidence": float(self.params["min_confidence"]),
            }
        }

    def get_latest_thoughts(self) -> Dict[str, str]:
        """Retorna el razonamiento matemático en tiempo real para la UI y logs."""
        return self.latest_thoughts
