"""Unit test script for generate_entry_chart_card."""
import os
import sys
from decimal import Decimal

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.telegram.visual_reporter import generate_entry_chart_card

# Mock 30 candles: [timestamp_ms, open, high, low, close, volume]
base_price = 1.0850
candles = []
for i in range(30):
    o = base_price + (i * 0.0001)
    h = o + 0.0003
    l = o - 0.0002
    c = o + 0.00015 if i % 2 == 0 else o - 0.0001
    candles.append([1700000000000 + i * 60000, o, h, l, c, 100])

# Test CALL
buf_call = generate_entry_chart_card(
    symbol="EURUSD-OTC",
    side="CALL",
    entry_price=Decimal("1.08795"),
    candles=candles,
    pattern_name="Martillo / Rechazo Alcista",
    reason="RSI en sobreventa (31.2) rebote inminente con cruce EMA 9 > 21",
    stake=Decimal("10.00"),
    mode_label="DEMO (IQ Option Práctica)"
)
call_bytes = buf_call.getvalue()
assert len(call_bytes) > 5000, f"CALL chart card too small: {len(call_bytes)}"
print(f"[OK] CALL Entry chart generated successfully ({len(call_bytes)} bytes)")

# Test PUT
buf_put = generate_entry_chart_card(
    symbol="EURUSD-OTC",
    side="PUT",
    entry_price=Decimal("1.08795"),
    candles=candles,
    pattern_name="Estrella Fugaz / Rechazo Bajista",
    reason="RSI en sobrecompra (68.4) agotamiento con cruce bajista EMA 9 < 21",
    stake=Decimal("20.00"),
    mode_label="DEMO (IQ Option Práctica)"
)
put_bytes = buf_put.getvalue()
assert len(put_bytes) > 5000, f"PUT chart card too small: {len(put_bytes)}"
print(f"[OK] PUT Entry chart generated successfully ({len(put_bytes)} bytes)")

print("\n[SUCCESS] Todos los tests de generacion de graficas de entrada pasaron con EXITO!")
