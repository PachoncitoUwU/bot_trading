"""Verification script for Bi-directional CALL/PUT signals and chart card broadcast."""
import asyncio
import os
import sys
from decimal import Decimal

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.core.constants import SignalType
from app.strategies.ai_learning_strategy import AILearningStrategy


async def test_bidirectional_signals():
    print("1. Probando generacion de senales Bi-Direccionales (CALL y PUT)...")
    strategy = AILearningStrategy(symbols=["EURUSD-OTC"], timeframe="1m")

    # Synthetic candles for CALL (oversold + hammer + lower BB touch)
    candles_call = []
    p = 1.1000
    for i in range(40):
        p -= 0.0008
        candles_call.append([1700000000000 + i * 60000, p + 0.0003, p + 0.0004, p - 0.0001, p, 100])
    
    # Final candle: hammer rejecting off lower BB
    last_open = p
    last_low = p - 0.0040
    last_close = p + 0.0003
    last_high = last_close + 0.0001
    candles_call.append([1700000000000 + 40 * 60000, last_open, last_high, last_low, last_close, 200])

    sigs_call = strategy.generate_signals({"EURUSD-OTC": candles_call}, {})
    print(f"   Senales CALL generadas: {len(sigs_call)}")
    for s in sigs_call:
        print(f"   -> [CALL] {s.symbol} Type={s.signal_type.value} Conf={s.confidence:.2f} Reason={s.reason[:60]}...")
    assert len(sigs_call) > 0, "Debe generar al menos una senal CALL"
    assert sigs_call[0].signal_type == SignalType.BUY, "La senal CALL debe tener SignalType.BUY"

    # Synthetic candles for PUT (overbought + shooting star + upper BB touch)
    candles_put = []
    p_up = 1.0500
    for i in range(40):
        p_up += 0.0008
        candles_put.append([1700000000000 + i * 60000, p_up - 0.0003, p_up + 0.0001, p_up - 0.0004, p_up, 100])
    
    # Final candle: shooting star rejecting off upper BB
    put_open = p_up
    put_high = p_up + 0.0040
    put_close = p_up - 0.0003
    put_low = put_close - 0.0001
    candles_put.append([1700000000000 + 40 * 60000, put_open, put_high, put_low, put_close, 200])

    sigs_put = strategy.generate_signals({"EURUSD-OTC": candles_put}, {})
    print(f"   Senales PUT generadas: {len(sigs_put)}")
    for s in sigs_put:
        print(f"   -> [PUT] {s.symbol} Type={s.signal_type.value} Conf={s.confidence:.2f} Reason={s.reason[:60]}...")
    assert len(sigs_put) > 0, "Debe generar al menos una senal PUT"
    assert sigs_put[0].signal_type == SignalType.SELL, "La senal PUT debe tener SignalType.SELL"

    # Test latest thoughts
    thoughts = strategy.get_latest_thoughts()
    print(f"   Pensamientos de la IA expuestos: {thoughts.get('EURUSD-OTC', '')}")
    assert "EURUSD-OTC" in thoughts, "Debe haber pensamientos registrados para EURUSD-OTC"

    print("\n[SUCCESS] Pruebas de Estrategia Bi-Direccional CALL/PUT completadas con EXITO!")


if __name__ == "__main__":
    asyncio.run(test_bidirectional_signals())
