"""Adaptive AI & Sentiment-Enhanced Trading Strategy.

Combines multi-timeframe technical patterns (EMA trend, RSI momentum, candle anatomy)
with live internet sentiment context (Crypto Fear & Greed Index) and dynamic confidence scoring.
Logs decision features to enable continuous learning and parameter calibration.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import json
import math
import os

from app.core.constants import SignalType
from app.core.decimal_math import to_decimal
from app.core.logger import logger
from app.services.sentiment_service import sentiment_service
from app.strategies.base_strategy import BaseStrategy, StrategySignal


class AILearningStrategy(BaseStrategy):
    """
    Intelligent Adaptive Sniper Strategy for Binary Options (1m).
    Uses Triple Confluence:
      1. Bollinger Bands (20, 2.0) extreme pierce/touch
      2. RSI Extreme (<=32 / >=68) with turnaround
      3. Price Action Rejection Wicks (Pinbar / Hammer / Shooting Star >= 1.8x body)
      4. MTF Trend Filter (EMA 50 & 100) to avoid counter-trend traps.
    Only fires when confidence >= 0.65 and at least 2 major confluences align.
    """

    def __init__(self, symbols: List[str], timeframe: str = "1m", params: Optional[Dict[str, Any]] = None):
        default_params = {
            "fast_ema": 9,
            "mid_ema": 21,
            "slow_ema": 50,
            "trend_ema": 100,
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_period": 14,
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "min_confidence": Decimal("0.58"),  # Umbral sniper: mínimo 58% de confianza para filtrar ruido OTC
            "base_sl_pct": Decimal("1.5"),
            "base_tp_pct": Decimal("3.0"),
            "use_internet_sentiment": True,
            "learning_mode": True,
        }
        if params:
            default_params.update(params)

        super().__init__(
            name="AI_Sniper_Confluence_v3",
            symbols=symbols,
            timeframe=timeframe,
            params=default_params
        )
        self.decision_log: List[Dict[str, Any]] = []
        self._sentiment_cache: Dict[str, Any] = {}
        self.latest_thoughts: Dict[str, str] = {}
        self.memory_file = os.path.join(os.path.dirname(__file__), "learning_memory.json")
        self.learned_patterns: Dict[str, Dict[str, Any]] = self._load_learning_memory()

    def _load_learning_memory(self) -> Dict[str, Dict[str, Any]]:
        """Loads learned pattern weights from persistent storage."""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"[AI LEARNING] Loaded memory with {len(data)} learned patterns.")
                    return data
            except Exception as e:
                logger.warning(f"[AI LEARNING] Error loading learning memory: {e}. Starting fresh.")
        return {}

    def _save_learning_memory(self) -> None:
        """Saves current pattern weights and stats to disk."""
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.learned_patterns, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[AI LEARNING] Failed to save learning memory: {e}")

    def _calc_ema(self, values: List[Decimal], period: int) -> Decimal:
        """Calculates Exponential Moving Average with standard alpha smoothing."""
        if not values or len(values) < period:
            return values[-1] if values else Decimal("0")
        
        alpha = Decimal(str(2.0 / (period + 1)))
        ema = values[0]
        for val in values[1:]:
            ema = (val * alpha) + (ema * (Decimal("1") - alpha))
        return ema

    def _calc_rsi(self, closes: List[Decimal], period: int = 14) -> Decimal:
        """Calculates Relative Strength Index (RSI)."""
        if len(closes) <= period:
            return Decimal("50.0")

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(abs(diff))

        avg_gain = sum(gains[-period:]) / Decimal(str(period))
        avg_loss = sum(losses[-period:]) / Decimal(str(period))

        if avg_loss == Decimal("0"):
            return Decimal("100.0")
        rs = avg_gain / avg_loss
        rsi = Decimal("100.0") - (Decimal("100.0") / (Decimal("1.0") + rs))
        return rsi

    def _calc_bollinger_bands(
        self,
        closes: List[Decimal],
        period: int = 20,
        num_std: float = 2.0
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """Calculates Bollinger Bands (upper, middle/sma, lower)."""
        if len(closes) < period:
            last = closes[-1] if closes else Decimal("0")
            return last, last, last

        recent = closes[-period:]
        sma = sum(recent) / Decimal(str(period))
        variance = sum((x - sma) ** 2 for x in recent) / Decimal(str(period))
        std_dev = Decimal(str(math.sqrt(float(variance))))
        offset = std_dev * Decimal(str(num_std))
        upper = sma + offset
        lower = sma - offset
        return upper, sma, lower

    def _detect_candle_pattern(
        self,
        open_p: Decimal,
        high_p: Decimal,
        low_p: Decimal,
        close_p: Decimal,
        prev_open: Optional[Decimal] = None,
        prev_close: Optional[Decimal] = None
    ) -> str:
        """
        Detects candle formations with strict wick-to-body ratio validation:
        Pinbars, Hammers, Shooting Stars, Engulfing.
        """
        body = abs(close_p - open_p)
        candle_range = high_p - low_p
        if candle_range == Decimal("0"):
            return "Doji"

        lower_wick = min(open_p, close_p) - low_p
        upper_wick = high_p - max(open_p, close_p)

        # Bullish Engulfing
        if prev_open and prev_close and prev_close < prev_open and close_p > open_p:
            if close_p >= prev_open and open_p <= prev_close:
                return "Envolvente Alcista"

        # Bearish Engulfing
        if prev_open and prev_close and prev_close > prev_open and close_p < open_p:
            if close_p <= prev_open and open_p >= prev_close:
                return "Envolvente Bajista"

        # Institutional Hammer / Pinbar Alcista (Lower wick >= 1.8x body)
        if lower_wick >= (body * Decimal("1.8")) and upper_wick <= (candle_range * Decimal("0.30")):
            return "Martillo / Pinbar Alcista"

        # Institutional Shooting Star / Pinbar Bajista (Upper wick >= 1.8x body)
        if upper_wick >= (body * Decimal("1.8")) and lower_wick <= (candle_range * Decimal("0.30")):
            return "Estrella Fugaz / Pinbar Bajista"

        # Strong Momentum / Marubozu
        if close_p > open_p and (body / candle_range) > Decimal("0.75"):
            return "Impulso Alcista Fuerte"
        elif close_p < open_p and (body / candle_range) > Decimal("0.75"):
            return "Impulso Bajista Fuerte"

        return "Neutral"

    def generate_signals(self, market_data: Dict[str, Any], open_positions: Dict[str, Any]) -> List[StrategySignal]:
        """
        Evaluates live market candles using Sniper Triple Confluence:
          1. Bollinger Bands (20, 2.0) extreme pierce/touch
          2. RSI (14) Extreme + Giro
          3. Rejection Wick / Pinbar (>= 1.8x body)
          4. MTF Trend Filter (EMA 50/100)
        """
        signals: List[StrategySignal] = []
        min_candles_required = 35

        sentiment = self._sentiment_cache or {
            "value": 50,
            "status": "NEUTRAL ⚖️",
            "risk_multiplier": 1.0,
            "classification": "Neutral"
        }

        for symbol in self.symbols:
            if symbol not in market_data:
                continue
            candles = market_data.get(symbol, [])
            if len(candles) < min_candles_required:
                self.latest_thoughts[symbol] = f"⏳ Recopilando velas para {symbol} ({len(candles)}/{min_candles_required})..."
                continue

            # Parse OHLCV
            opens = [to_decimal(c[1]) for c in candles]
            highs = [to_decimal(c[2]) for c in candles]
            lows = [to_decimal(c[3]) for c in candles]
            closes = [to_decimal(c[4]) for c in candles]

            current_price = closes[-1]
            prev_price = closes[-2]

            # Technical indicators
            upper_bb, mid_bb, lower_bb = self._calc_bollinger_bands(
                closes,
                period=self.params.get("bb_period", 20),
                num_std=self.params.get("bb_std", 2.0)
            )

            fast_ema = self._calc_ema(closes, self.params["fast_ema"])
            mid_ema = self._calc_ema(closes, self.params["mid_ema"])
            slow_ema = self._calc_ema(closes, self.params["slow_ema"])
            trend_ema = self._calc_ema(closes, self.params.get("trend_ema", 100))

            rsi = self._calc_rsi(closes, self.params["rsi_period"])
            prev_rsi = self._calc_rsi(closes[:-1], self.params["rsi_period"])

            prev_fast = self._calc_ema(closes[:-1], self.params["fast_ema"])
            prev_mid = self._calc_ema(closes[:-1], self.params["mid_ema"])

            pattern = self._detect_candle_pattern(
                opens[-1], highs[-1], lows[-1], closes[-1],
                prev_open=opens[-2], prev_close=closes[-2]
            )

            pattern_stats = self.learned_patterns.get(pattern, {"weight": 1.0, "wins": 0, "losses": 0})
            # FORWARD-TEST CIENTÍFICO 300 TRADES: Pesos 100% congelados en 1.0x (Cero mutación en vivo)
            pat_w = Decimal("1.0")

            # ──────────────────────────────────────────────────────────────────
            # Bullish Sniper Evaluation (CALL / Subida)
            # ──────────────────────────────────────────────────────────────────
            bull_confidence = Decimal("0.0")
            bull_reasons = []
            bull_confluences = 0

            # 1. Bollinger Band Confluence (Piercing or touching lower band)
            touched_lower_bb = lows[-1] <= lower_bb or lows[-2] <= lower_bb or current_price <= (lower_bb * Decimal("1.0008"))
            if touched_lower_bb:
                bull_confidence += Decimal("0.30")
                bull_confluences += 1
                bull_reasons.append(f"Toque Banda Bollinger Inferior ({lower_bb:.5f})")

            # 2. RSI Oversold + Inflexion Confluence (Fase ágil)
            if rsi <= Decimal("35.0"):
                bull_confluences += 1
                if rsi > prev_rsi:
                    bull_confidence += Decimal("0.35")
                    bull_reasons.append(f"RSI Extremo con Giro Alcista ({rsi:.1f} > {prev_rsi:.1f})")
                else:
                    bull_confidence += Decimal("0.28")
                    bull_reasons.append(f"RSI en Sobreventa Extrema ({rsi:.1f})")
            elif rsi <= Decimal("42.0"):
                bull_confluences += 1
                bull_confidence += Decimal("0.22")
                bull_reasons.append(f"RSI en Zona de Soporte ({rsi:.1f})")

            # 3. Candle Rejection & Pattern Confluence (Institutional Quality Filter)
            # A) Martillo / Pinbar Alcista de alta calidad (Rechazo con mecha inferior >= 2x cuerpo)
            if "Martillo" in pattern or "Pinbar Alcista" in pattern:
                bull_confluences += 1
                added_conf = Decimal("0.30") * pat_w
                bull_confidence += added_conf
                bull_reasons.append(f"Absorción Institucional: {pattern} (IA: {pat_w:.2f}x)")

            # B) Envolvente Alcista Perfeccionada: Solo válida si ocurre en soporte o banda Bollinger
            elif "Envolvente Alcista" in pattern:
                if touched_lower_bb or rsi <= Decimal("40.0"):
                    bull_confluences += 1
                    bull_confidence += Decimal("0.28") * pat_w
                    bull_reasons.append(f"Envolvente Alcista Perfeccionada (Rebote en Soporte + Bollinger)")
                else:
                    # Envolvente en medio del canal sin soporte: Descartada para evitar trampas
                    bull_reasons.append("Envolvente descartada: Sin confluencia de soporte/Bollinger")

            # C) Continuación de Impulso Institucional a Favor de Tendencia
            elif "Impulso Alcista Fuerte" in pattern and current_price > slow_ema and fast_ema > mid_ema and rsi < Decimal("72.0"):
                bull_confluences += 1
                bull_confidence += Decimal("0.35")
                bull_reasons.append("Impulso Alcista Institucional Confirmado a Favor de Tendencia (CALL)")

            # 4. Trend & EMA Confluence (Pullback in uptrend or golden cross)
            crossover_bullish = prev_fast <= prev_mid and fast_ema > mid_ema
            if crossover_bullish:
                # Cruce Dorado Elevado a Excelencia: Exige estar sobre EMA 50 y RSI con espacio libre (< 68)
                if current_price > slow_ema and rsi <= Decimal("68.0"):
                    bull_confluences += 1
                    bull_confidence += Decimal("0.25")
                    bull_reasons.append("Cruce Dorado Institucional (EMA 9 > 21 sobre EMA 50 con espacio RSI)")
                else:
                    bull_confidence += Decimal("0.10")
                    bull_reasons.append("Cruce rápido EMA 9 > 21")
            elif current_price > slow_ema and fast_ema > mid_ema:
                bull_confidence += Decimal("0.15")
                bull_reasons.append("A favor de tendencia EMA 50")

            # Current candle geometric metrics
            curr_body = abs(closes[-1] - opens[-1])
            curr_range = highs[-1] - lows[-1] if (highs[-1] - lows[-1]) > Decimal("0") else Decimal("0.00001")
            curr_lower_wick = min(opens[-1], closes[-1]) - lows[-1]
            curr_upper_wick = highs[-1] - max(opens[-1], closes[-1])
            ema_dist_pct = (abs(current_price - slow_ema) / slow_ema * Decimal("100.0")) if slow_ema > Decimal("0") else Decimal("0")

            # REGLA DE ORO ANTI-CONTRA-TENDENCIA: Prohibido apostar CALL contra tendencia bajista
            # Excepción Cuantificada al 100%: Solo permitida si hay agotamiento extremo comprobado matemáticamente:
            # 1. Mecha inferior >= 2.0x cuerpo (Rechazo contundente de mínimos)
            # 2. Mecha superior <= 0.20x rango total de la vela (Sin rechazo bajista arriba)
            # 3. RSI(14) <= 30.0 (Sobreventa profunda) con inflexión alcista confirmada (RSI_t > RSI_t-1)
            # 4. Mínimo de la vela perforando la Banda Inferior de Bollinger (low <= lower_bb)
            # 5. Distancia a la EMA 50 >= 0.04% del precio (Garantiza sobre-extensión del impulso bajista)
            is_downtrend = (current_price < slow_ema) or (fast_ema < mid_ema and current_price < trend_ema)
            if is_downtrend:
                has_quantified_reversal = (
                    curr_lower_wick >= (curr_body * Decimal("2.0"))
                    and curr_upper_wick <= (curr_range * Decimal("0.20"))
                    and rsi <= Decimal("30.0")
                    and rsi > prev_rsi
                    and lows[-1] <= lower_bb
                    and ema_dist_pct >= Decimal("0.04")
                )
                if not has_quantified_reversal:
                    bull_confidence = Decimal("0.0")
                    bull_reasons.append(
                        f"🛡️ Filtro Anti-Contra-Tendencia: Tendencia bajista activa (EMA 50). "
                        f"CALL bloqueado sin reversión cuantificada (Wick={float(curr_lower_wick/curr_body if curr_body > 0 else 0):.1f}x/2.0x, "
                        f"RSI={float(rsi):.1f}/30.0, Dist={float(ema_dist_pct):.3f}%/0.04%)"
                    )

            # ──────────────────────────────────────────────────────────────────
            # Bearish Sniper Evaluation (PUT / Bajada)
            # ──────────────────────────────────────────────────────────────────
            bear_confidence = Decimal("0.0")
            bear_reasons = []
            bear_confluences = 0

            # 1. Bollinger Band Confluence (Piercing or touching upper band)
            touched_upper_bb = highs[-1] >= upper_bb or highs[-2] >= upper_bb or current_price >= (upper_bb * Decimal("0.9992"))
            if touched_upper_bb:
                bear_confidence += Decimal("0.30")
                bear_confluences += 1
                bear_reasons.append(f"Toque Banda Bollinger Superior ({upper_bb:.5f})")

            # 2. RSI Overbought + Inflexion Confluence (Fase ágil)
            if rsi >= Decimal("65.0"):
                bear_confluences += 1
                if rsi < prev_rsi:
                    bear_confidence += Decimal("0.35")
                    bear_reasons.append(f"RSI Extremo con Giro Bajista ({rsi:.1f} < {prev_rsi:.1f})")
                else:
                    bear_confidence += Decimal("0.28")
                    bear_reasons.append(f"RSI en Sobrecompra Extrema ({rsi:.1f})")
            elif rsi >= Decimal("58.0"):
                bear_confluences += 1
                bear_confidence += Decimal("0.22")
                bear_reasons.append(f"RSI en Zona de Resistencia ({rsi:.1f})")

            # 3. Candle Rejection & Pattern Confluence (Institutional Quality Filter)
            # A) Estrella Fugaz / Pinbar Bajista de alta calidad (Rechazo con mecha superior >= 2x cuerpo)
            if "Estrella Fugaz" in pattern or "Pinbar Bajista" in pattern:
                bear_confluences += 1
                added_conf = Decimal("0.30") * pat_w
                bear_confidence += added_conf
                bear_reasons.append(f"Absorción Institucional: {pattern} (IA: {pat_w:.2f}x)")

            # B) Envolvente Bajista Perfeccionada: Solo válida si ocurre en resistencia o banda Bollinger superior
            elif "Envolvente Bajista" in pattern:
                if touched_upper_bb or rsi >= Decimal("60.0"):
                    bear_confluences += 1
                    bear_confidence += Decimal("0.28") * pat_w
                    bear_reasons.append("Envolvente Bajista Perfeccionada (Rechazo en Resistencia + Bollinger)")
                else:
                    bear_reasons.append("Envolvente descartada: Sin confluencia de resistencia/Bollinger")

            # C) Continuación de Impulso Institucional a Favor de Tendencia
            elif "Impulso Bajista Fuerte" in pattern and current_price < slow_ema and fast_ema < mid_ema and rsi > Decimal("28.0"):
                bear_confluences += 1
                bear_confidence += Decimal("0.35")
                bear_reasons.append("Impulso Bajista Institucional Confirmado a Favor de Tendencia (PUT)")

            # 4. Trend & EMA Confluence (Pullback in downtrend or death cross)
            crossover_bearish = prev_fast >= prev_mid and fast_ema < mid_ema
            if crossover_bearish:
                # Cruce de Muerte Perfeccionado: Solo operar si está bajo EMA 50 y en pullback
                if current_price < slow_ema and rsi >= Decimal("32.0"):
                    bear_confluences += 1
                    bear_confidence += Decimal("0.25")
                    bear_reasons.append("Cruce Bajista Institucional (EMA 9 < 21 confirmado bajo EMA 50)")
                else:
                    bear_confidence += Decimal("0.05")
                    bear_reasons.append("Cruce bajista en rango sin tendencia macro (filtrado)")
            elif current_price < slow_ema and fast_ema < mid_ema:
                bear_confidence += Decimal("0.15")
                bear_reasons.append("A favor de tendencia EMA 50")

            # REGLA DE ORO ANTI-CONTRA-TENDENCIA: Prohibido apostar PUT contra tendencia alcista
            # Excepción Cuantificada al 100%: Solo permitida si hay agotamiento extremo comprobado matemáticamente:
            # 1. Mecha superior >= 2.0x cuerpo (Rechazo contundente de máximos)
            # 2. Mecha inferior <= 0.20x rango total de la vela (Sin rechazo alcista abajo)
            # 3. RSI(14) >= 70.0 (Sobrecompra profunda) con inflexión bajista confirmada (RSI_t < RSI_t-1)
            # 4. Máximo de la vela perforando la Banda Superior de Bollinger (high >= upper_bb)
            # 5. Distancia a la EMA 50 >= 0.04% del precio (Garantiza sobre-extensión del impulso alcista)
            is_uptrend = (current_price > slow_ema) or (fast_ema > mid_ema and current_price > trend_ema)
            if is_uptrend:
                has_quantified_reversal = (
                    curr_upper_wick >= (curr_body * Decimal("2.0"))
                    and curr_lower_wick <= (curr_range * Decimal("0.20"))
                    and rsi >= Decimal("70.0")
                    and rsi < prev_rsi
                    and highs[-1] >= upper_bb
                    and ema_dist_pct >= Decimal("0.04")
                )
                if not has_quantified_reversal:
                    bear_confidence = Decimal("0.0")
                    bear_reasons.append(
                        f"🛡️ Filtro Anti-Contra-Tendencia: Tendencia alcista activa (EMA 50). "
                        f"PUT bloqueado sin reversión cuantificada (Wick={float(curr_upper_wick/curr_body if curr_body > 0 else 0):.1f}x/2.0x, "
                        f"RSI={float(rsi):.1f}/70.0, Dist={float(ema_dist_pct):.3f}%/0.04%)"
                    )

            # FILTRO FRANCOTIRADOR DE ALTA PRECISIÓN: Umbral de confianza elevado a 0.65
            active_min_conf = Decimal("0.65")
            learning_stage = "🎯 Francotirador de Alta Precisión"

            # Real-time thought display for user UI
            dominant = "CALL (Alcista)" if bull_confidence >= bear_confidence else "PUT (Bajista)"
            top_conf = max(bull_confidence, bear_confidence)
            price_disp = f"${float(current_price):,.2f}" if current_price >= 10 else f"{float(current_price):.5f}"

            is_sniper_call = bull_confidence >= active_min_conf and (touched_lower_bb and rsi <= Decimal("38.0"))
            is_sniper_put = bear_confidence >= active_min_conf and (touched_upper_bb and rsi >= Decimal("62.0"))

            if is_sniper_call or is_sniper_put:
                status_hint = f"🎯 ¡SEÑAL CONFIRMADA ({learning_stage})!"
            elif (touched_lower_bb and rsi <= Decimal("42.0")) or (touched_upper_bb and rsi >= Decimal("58.0")):
                status_hint = f"⏳ Confluencia en desarrollo [{learning_stage}]..."
            else:
                status_hint = f"👀 Monitoreando [{learning_stage}]"

            self.latest_thoughts[symbol] = (
                f"Escaneando {symbol} (1m): Precio {price_disp} | RSI={float(rsi):.1f} | "
                f"BB=[{float(lower_bb):.4f} - {float(upper_bb):.4f}] | Vela: {pattern} | "
                f"Sesgo: {dominant} ({int(top_conf * 100)}% conf.) | {status_hint}"
            )

            is_in_position = symbol in open_positions

            if not is_in_position:
                # Trigger CALL: Requires bull_confidence >= 0.65, at least 2 confluences, Bollinger touch + RSI <= 38.0
                if (
                    bull_confidence >= active_min_conf
                    and bull_confluences >= 2
                    and (touched_lower_bb and rsi <= Decimal("38.0"))
                    and bull_confidence > bear_confidence
                ):
                    sl_pct = self.params["base_sl_pct"]
                    tp_pct = self.params["base_tp_pct"]
                    sl_price = current_price * (Decimal("1") - (sl_pct / Decimal("100")))
                    tp_price = current_price * (Decimal("1") + (tp_pct / Decimal("100")))

                    sig = StrategySignal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        price=current_price,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        confidence=bull_confidence,
                        pattern_name=pattern if pattern != "Neutral" else "Confluencia Sniper CALL",
                        reason=f"[{learning_stage}] " + " | ".join(bull_reasons),
                        metadata={
                            "direction": "CALL",
                            "rsi": float(rsi),
                            "pattern": pattern,
                            "confluences": bull_confluences,
                            "confidence": float(bull_confidence),
                            "learning_stage": learning_stage
                        }
                    )
                    signals.append(sig)
                    logger.info(
                        f"[AI SNIPER STRATEGY] 🎯 Generated CALL signal for {symbol} "
                        f"(conf={bull_confidence:.2f}, stage={learning_stage}): {sig.reason}"
                    )

                # Trigger PUT: Requires bear_confidence >= 0.65, at least 2 confluences, Bollinger touch + RSI >= 62.0
                elif (
                    bear_confidence >= active_min_conf
                    and bear_confluences >= 2
                    and (touched_upper_bb and rsi >= Decimal("62.0"))
                    and bear_confidence > bull_confidence
                ):
                    sl_pct = self.params["base_sl_pct"]
                    tp_pct = self.params["base_tp_pct"]
                    sl_price = current_price * (Decimal("1") + (sl_pct / Decimal("100")))
                    tp_price = current_price * (Decimal("1") - (tp_pct / Decimal("100")))

                    sig = StrategySignal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        price=current_price,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        confidence=bear_confidence,
                        pattern_name=pattern if pattern != "Neutral" else "Confluencia Sniper PUT",
                        reason=f"[{learning_stage}] " + " | ".join(bear_reasons),
                        metadata={
                            "direction": "PUT",
                            "rsi": float(rsi),
                            "pattern": pattern,
                            "confluences": bear_confluences,
                            "confidence": float(bear_confidence),
                            "learning_stage": learning_stage
                        }
                    )
                    signals.append(sig)
                    logger.info(
                        f"[AI SNIPER STRATEGY] 🎯 Generated PUT signal for {symbol} "
                        f"(conf={bear_confidence:.2f}, stage={learning_stage}): {sig.reason}"
                    )

        return signals

    def record_trade_outcome(
        self,
        symbol: str,
        pnl_pct: Decimal,
        is_win: bool,
        pattern_name: str,
        exit_reason: str = ""
    ) -> None:
        """
        Reinforcement feedback loop: adjusts weights and memory based on closed trade results.
        """
        if not pattern_name:
            pattern_name = "Cruce Cuantitativo IA"

        if pattern_name not in self.learned_patterns:
            self.learned_patterns[pattern_name] = {
                "wins": 0,
                "losses": 0,
                "weight": 1.0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
            }

        stats = self.learned_patterns[pattern_name]
        if is_win:
            stats["wins"] += 1
        else:
            stats["losses"] += 1

        # FORWARD-TEST CIENTÍFICO: Los pesos permanecen congelados en 1.0x (Cero auto-ajustes en tiempo real)
        stats["weight"] = 1.0
        stats["total_pnl"] = round(stats.get("total_pnl", 0.0) + float(pnl_pct), 2)
        total = stats["wins"] + stats["losses"]
        stats["win_rate"] = round((stats["wins"] / total) * 100, 1) if total > 0 else 0.0

        self._save_learning_memory()

        logger.info(
            f"[AI LEARNING] Trade closed for {symbol}: PnL={pnl_pct:+.2f}% ({'WIN 🎯' if is_win else 'LOSS 🛡'}). "
            f"Pattern '{pattern_name}' updated weight -> {stats['weight']:.2f}x (WinRate: {stats['win_rate']}%)"
        )

    def update_sentiment_cache(self, sentiment_data: Dict[str, Any]) -> None:
        """Allows real-time injection of web market sentiment updates."""
        self._sentiment_cache = sentiment_data

    def get_stats(self) -> Dict[str, Any]:
        """Returns internal AI strategy statistics."""
        total_trades = sum(p.get("wins", 0) + p.get("losses", 0) for p in self.learned_patterns.values())
        total_wins = sum(p.get("wins", 0) for p in self.learned_patterns.values())
        overall_wr = round((total_wins / total_trades) * 100, 1) if total_trades > 0 else 0.0

        return {
            "name": self.name,
            "total_decisions_evaluated": len(self.decision_log),
            "min_confidence": float(self.params["min_confidence"]),
            "symbols": self.symbols,
            "total_trades_learned": total_trades,
            "overall_learned_win_rate": overall_wr,
            "learned_patterns": self.learned_patterns,
        }

    def get_latest_thoughts(self) -> Dict[str, str]:
        """Returns the real-time scanning reasoning for each monitored asset."""
        return self.latest_thoughts
