"""Market Intelligence & Sentiment Analysis Service.

Fetches real-time market sentiment (Crypto Fear & Greed Index, Macro Trends)
from public web APIs to provide macro context and risk adjustment for trading strategies.
"""
import time
from typing import Any, Dict, Optional
import httpx

from app.core.logger import logger


class MarketIntelligenceService:
    """Provides real-time internet-based market sentiment and intelligence."""

    FNG_API_URL = "https://api.alternative.me/fng/?limit=1"

    def __init__(self, cache_ttl_seconds: int = 600):
        self.cache_ttl = cache_ttl_seconds
        self._cached_data: Optional[Dict[str, Any]] = None
        self._last_fetch_time: float = 0.0

    async def get_sentiment(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches current Fear & Greed Index from the internet.
        Uses caching to prevent excessive API requests.
        Returns dictionary with score, classification, and trading context.
        """
        now = time.time()
        if not force_refresh and self._cached_data and (now - self._last_fetch_time < self.cache_ttl):
            return self._cached_data

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(self.FNG_API_URL)
                response.raise_for_status()
                payload = response.json()

            data_list = payload.get("data", [])
            if data_list:
                item = data_list[0]
                value = int(item.get("value", 50))
                value_classification = item.get("value_classification", "Neutral")

                # Contextualize for Trading Bot
                if value <= 25:
                    status = "PÁNICO EXTREMO 😱"
                    strategy_advice = "Alta probabilidad de rebotes o ventas de pánico. Operar con Stop Loss ceñido y menor apalancamiento."
                    risk_multiplier = 0.75  # Cautela en compras
                elif value <= 45:
                    status = "MIEDO 😨"
                    strategy_advice = "Mercado escéptico. Buenas oportunidades en soportes confirmados."
                    risk_multiplier = 0.9
                elif value <= 55:
                    status = "NEUTRAL ⚖️"
                    strategy_advice = "Mercado equilibrado. Priorizar confirmaciones técnicas puras."
                    risk_multiplier = 1.0
                elif value <= 75:
                    status = "CODICIA / OPTIMISMO 🚀"
                    strategy_advice = "Tendencia alcista fuerte. Dejar correr ganancias con Trailing Stop."
                    risk_multiplier = 1.0
                else:
                    status = "EUFORIA EXTREMA ⚠️"
                    strategy_advice = "Riesgo alto de corrección abrupta. Evitar comprar en techos."
                    risk_multiplier = 0.8  # Reducir sobreexposición

                result = {
                    "value": value,
                    "status": status,
                    "classification": value_classification,
                    "strategy_advice": strategy_advice,
                    "risk_multiplier": risk_multiplier,
                    "timestamp": item.get("timestamp"),
                    "is_live": True,
                }
                self._cached_data = result
                self._last_fetch_time = now
                logger.info(f"[SENTIMENT] Live sentiment fetched: {value} ({status})")
                return result

        except Exception as e:
            logger.warning(f"[SENTIMENT] Could not fetch live sentiment from web: {e}. Using fallback neutral state.")
            # Fallback safe state so trading never breaks if internet has a hiccup
            if self._cached_data:
                return self._cached_data

        return {
            "value": 50,
            "status": "NEUTRAL (FALLBACK) ⚖️",
            "classification": "Neutral",
            "strategy_advice": "Operación estándar con parámetros técnicos.",
            "risk_multiplier": 1.0,
            "timestamp": str(int(now)),
            "is_live": False,
        }


sentiment_service = MarketIntelligenceService()
