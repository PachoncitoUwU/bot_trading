"""Unit test script for generate_result_chart_card."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.telegram.visual_reporter import generate_result_chart_card

# Mock 25 candles
base_price = 1.0850
candles = []
for i in range(25):
    o = base_price + (i * 0.0001)
    h = o + 0.0003
    l = o - 0.0002
    c = o + 0.0002 if i % 2 == 0 else o - 0.0001
    candles.append([1700000000000 + i * 60000, o, h, l, c, 100])

# Test WIN result card (2m duration)
buf_win = generate_result_chart_card(
    symbol="EURUSD-OTC",
    side="CALL",
    entry_price=Decimal("1.08600"),
    exit_price=Decimal("1.08750"),
    net_pnl=Decimal("18.50"),
    pnl_pct=Decimal("85.0"),
    candles=candles,
    duration_minutes=2,
    pattern_name="Martillo / Rebote RSI",
    is_win=True,
    stake=Decimal("10.00"),
    account_equity=Decimal("10125.50"),
    mode_label="DEMO (IQ Option Práctica)"
)
win_bytes = buf_win.getvalue()
assert len(win_bytes) > 5000, f"WIN chart card too small: {len(win_bytes)}"
print(f"[OK] WIN Result chart generated successfully ({len(win_bytes)} bytes)")

# Test LOSS result card (5m duration)
buf_loss = generate_result_chart_card(
    symbol="USDJPY-OTC",
    side="PUT",
    entry_price=Decimal("154.200"),
    exit_price=Decimal("154.350"),
    net_pnl=Decimal("-10.00"),
    pnl_pct=Decimal("-100.0"),
    candles=candles,
    duration_minutes=5,
    pattern_name="Estrella Fugaz",
    is_win=False,
    stake=Decimal("10.00"),
    account_equity=Decimal("10115.50"),
    mode_label="DEMO (IQ Option Práctica)"
)
loss_bytes = buf_loss.getvalue()
assert len(loss_bytes) > 5000, f"LOSS chart card too small: {len(loss_bytes)}"
print(f"[OK] LOSS Result chart generated successfully ({len(loss_bytes)} bytes)")

print("\n[SUCCESS] Todos los tests de generacion de tarjeta de resultado pasaron con EXITO!")
