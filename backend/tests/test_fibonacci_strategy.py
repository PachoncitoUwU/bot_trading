"""Test Suite for Fibonacci Retracement Strategy (Quantitative Golden Pocket)."""
import unittest
from decimal import Decimal
import time

from app.core.constants import SignalType
from app.strategies.fibonacci_strategy import FibonacciRetracementStrategy


class TestFibonacciRetracementStrategy(unittest.TestCase):

    def setUp(self):
        self.symbols = ["EURUSD-OTC"]
        self.strategy = FibonacciRetracementStrategy(
            symbols=self.symbols,
            timeframe="1m",
            params={
                "swing_window": 30,
                "min_impulse_pct": Decimal("0.05"),
                "tolerance_pct": Decimal("0.05"),
                "trend_ema": 20,
                "macro_ema": 50,
                "rsi_period": 14,
                "min_confidence": Decimal("0.70"),
                "rejection_wick_ratio": Decimal("1.0"),
            }
        )

    def test_fib_levels_calculation_bullish(self):
        """Verifies exact mathematical calculations of bullish retracement levels."""
        # Low at 1.0000, High at 2.0000 -> Diff = 1.0000
        sw_low = Decimal("1.0000")
        sw_high = Decimal("2.0000")
        levels = self.strategy._calculate_fib_levels(sw_high, sw_low, trend="BULLISH")

        # In bullish, retracement from high towards low:
        # Fib 38.2% = 2.0 - (1.0 * 0.382) = 1.618
        # Fib 50.0% = 2.0 - (1.0 * 0.500) = 1.500
        # Fib 61.8% = 2.0 - (1.0 * 0.618) = 1.382
        # Fib 78.6% = 2.0 - (1.0 * 0.786) = 1.214
        self.assertAlmostEqual(float(levels["FIB_382"]), 1.618, places=4)
        self.assertAlmostEqual(float(levels["FIB_500"]), 1.500, places=4)
        self.assertAlmostEqual(float(levels["FIB_618"]), 1.382, places=4)
        self.assertAlmostEqual(float(levels["FIB_786"]), 1.214, places=4)

    def test_fib_levels_calculation_bearish(self):
        """Verifies exact mathematical calculations of bearish retracement levels."""
        # High at 2.0000, Low at 1.0000 -> Diff = 1.0000
        sw_low = Decimal("1.0000")
        sw_high = Decimal("2.0000")
        levels = self.strategy._calculate_fib_levels(sw_high, sw_low, trend="BEARISH")

        # In bearish, retracement from low towards high:
        # Fib 38.2% = 1.0 + (1.0 * 0.382) = 1.382
        # Fib 50.0% = 1.0 + (1.0 * 0.500) = 1.500
        # Fib 61.8% = 1.0 + (1.0 * 0.618) = 1.618
        # Fib 78.6% = 1.0 + (1.0 * 0.786) = 1.786
        self.assertAlmostEqual(float(levels["FIB_382"]), 1.382, places=4)
        self.assertAlmostEqual(float(levels["FIB_500"]), 1.500, places=4)
        self.assertAlmostEqual(float(levels["FIB_618"]), 1.618, places=4)
        self.assertAlmostEqual(float(levels["FIB_786"]), 1.786, places=4)

    def test_bullish_golden_pocket_signal(self):
        """Creates a synthetic bullish impulse with a 61.8% pullback and rejection candle."""
        candles = []
        now = int(time.time() * 1000)
        base_price = Decimal("1.1000")

        # 1. 25 base candles around 1.1000
        for i in range(25):
            p = base_price + Decimal(str(i * 0.0001))
            candles.append([now + i * 60000, float(p), float(p + Decimal("0.0003")), float(p - Decimal("0.0001")), float(p + Decimal("0.0002")), 100.0])

        # 2. Strong impulse up to 1.1100 (Swing Low was ~1.1020, Swing High becomes 1.1100)
        # Rango = ~0.0080
        # 61.8% de retroceso: 1.1100 - (0.0080 * 0.618) = ~1.1050
        for i in range(15):
            p = Decimal("1.1020") + Decimal(str(i * 0.00055))
            candles.append([now + (25 + i) * 60000, float(p), float(p + Decimal("0.0004")), float(p - Decimal("0.0001")), float(p + Decimal("0.0003")), 150.0])

        # 3. Pullback down towards 1.1050 (61.8% golden level)
        candles.append([now + 41 * 60000, 1.1090, 1.1092, 1.1070, 1.1072, 120.0])
        candles.append([now + 42 * 60000, 1.1070, 1.1072, 1.1055, 1.1058, 120.0])

        # 4. Trigger candle: Touches 1.1050 with long lower rejection wick (Hammer)
        # Open 1.1058, High 1.1062, Low 1.1048 (touches Fib 61.8%), Close 1.1060
        # Lower wick = 1.1058 - 1.1048 = 0.0010, Body = 0.0002 -> Wick ratio = 5.0x
        candles.append([now + 43 * 60000, 1.1058, 1.1062, 1.1048, 1.1060, 180.0])

        market_data = {"EURUSD-OTC": candles}
        signals = self.strategy.generate_signals(market_data, {})

        # Should generate a CALL (BUY) signal
        self.assertGreaterEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig.symbol, "EURUSD-OTC")
        self.assertEqual(sig.signal_type, SignalType.BUY)
        self.assertIn("FIB_CALL", sig.pattern_name)
        self.assertGreaterEqual(sig.confidence, Decimal("0.70"))
        self.assertIn("EURUSD-OTC", self.strategy.get_latest_thoughts())

    def test_bearish_golden_pocket_signal(self):
        """Creates a synthetic bearish impulse with a 61.8% pullback and rejection candle."""
        candles = []
        now = int(time.time() * 1000)
        base_price = Decimal("1.2000")

        # 1. Base candles
        for i in range(25):
            p = base_price - Decimal(str(i * 0.0001))
            candles.append([now + i * 60000, float(p), float(p + Decimal("0.0001")), float(p - Decimal("0.0003")), float(p - Decimal("0.0002")), 100.0])

        # 2. Strong drop down to 1.1900
        # Swing High ~1.1980, Swing Low 1.1900 -> Rango 0.0080
        # 61.8% pullback upwards: 1.1900 + (0.0080 * 0.618) = ~1.1949
        for i in range(15):
            p = Decimal("1.1980") - Decimal(str(i * 0.00055))
            candles.append([now + (25 + i) * 60000, float(p), float(p + Decimal("0.0001")), float(p - Decimal("0.0004")), float(p - Decimal("0.0003")), 150.0])

        # 3. Pullback up towards 1.1950
        candles.append([now + 41 * 60000, 1.1910, 1.1930, 1.1908, 1.1928, 120.0])
        candles.append([now + 42 * 60000, 1.1930, 1.1945, 1.1928, 1.1942, 120.0])

        # 4. Trigger candle: Touches 1.1950 with long upper rejection wick (Shooting Star)
        # Open 1.1942, High 1.1952 (touches Fib 61.8%), Low 1.1938, Close 1.1940
        # Upper wick = 1.1952 - 1.1942 = 0.0010, Body = 0.0002 -> Wick ratio = 5.0x
        candles.append([now + 43 * 60000, 1.1942, 1.1952, 1.1938, 1.1940, 180.0])

        market_data = {"EURUSD-OTC": candles}
        signals = self.strategy.generate_signals(market_data, {})

        # Should generate a PUT (SELL) signal
        self.assertGreaterEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig.symbol, "EURUSD-OTC")
        self.assertEqual(sig.signal_type, SignalType.SELL)
        self.assertIn("FIB_PUT", sig.pattern_name)
        self.assertGreaterEqual(sig.confidence, Decimal("0.70"))

    def test_flat_range_filtering(self):
        """Ensures no signal is emitted if price is in a flat/dead sideways consolidation."""
        candles = []
        now = int(time.time() * 1000)
        # All candles within 0.00005 flat range
        for i in range(45):
            candles.append([now + i * 60000, 1.08000, 1.08003, 1.07998, 1.08001, 50.0])

        market_data = {"EURUSD-OTC": candles}
        signals = self.strategy.generate_signals(market_data, {})
        self.assertEqual(len(signals), 0)
        self.assertIn("Rango plano", self.strategy.get_latest_thoughts()["EURUSD-OTC"])

    def test_record_outcome_and_stats(self):
        """Verifies stats tracking by Fibonacci level."""
        self.strategy.record_trade_outcome("EURUSD-OTC", Decimal("85.0"), True, "FIB_CALL_FIB_618")
        self.strategy.record_trade_outcome("EURUSD-OTC", Decimal("85.0"), True, "FIB_CALL_FIB_618")
        self.strategy.record_trade_outcome("EURUSD-OTC", Decimal("-100.0"), False, "FIB_CALL_FIB_618")

        stats = self.strategy.get_stats()
        self.assertEqual(stats["stats_by_level"]["FIB_618"]["wins"], 2)
        self.assertEqual(stats["stats_by_level"]["FIB_618"]["losses"], 1)
        self.assertEqual(stats["stats_by_level"]["FIB_618"]["win_rate"], 66.7)


if __name__ == "__main__":
    unittest.main()
