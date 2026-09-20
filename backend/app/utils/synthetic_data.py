"""Synthetic OHLCV data generators for testing and cold-start backtest fallback.

This module replaces the generate_synthetic_ohlcv_trend() function that was
previously in verify_phase3.py (a testing script in the project root).
Moving it here makes it importable from within the app regardless of the
working directory — fixing the ModuleNotFoundError that occurred in Docker.
"""
import math
from typing import Any, List


def generate_synthetic_ohlcv_trend(n_bars: int = 200, base_price: float = 50_000.0) -> List[List[Any]]:
    """
    Generates synthetic OHLCV candlestick bars with oscillating price action.

    Designed to produce multiple MA crossover events, making it useful for
    testing strategy signal generation and backtest engine execution without
    requiring a live exchange connection.

    Args:
        n_bars: Number of 1-hour bars to generate.
        base_price: Starting price level in USD.

    Returns:
        List of [timestamp, open, high, low, close, volume] lists.
    """
    candles = []
    for i in range(n_bars):
        wave = math.sin(i / 8.0) * 800.0 + (i * 10.0)
        close = base_price + wave
        open_p = close - 20.0
        high_p = max(open_p, close) + 50.0
        low_p = min(open_p, close) - 50.0
        volume = 100.0
        timestamp = 1_700_000_000 + (i * 3600)  # Unix timestamps, 1h apart
        candles.append([timestamp, open_p, high_p, low_p, close, volume])
    return candles
