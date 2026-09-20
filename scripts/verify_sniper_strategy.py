import sys
import os
from decimal import Decimal

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.strategies.ai_learning_strategy import AILearningStrategy

def test_sniper_strategy():
    print("=== TEST 1: INICIALIZACIÓN ESTRATEGIA SNIPER ===")
    strat = AILearningStrategy(symbols=["EURUSD-OTC", "GBPUSD-OTC"])
    assert strat.params["min_confidence"] == Decimal("0.65"), f"Expected 0.65, got {strat.params['min_confidence']}"
    assert strat.params["rsi_oversold"] == 32
    assert strat.params["rsi_overbought"] == 68
    print("Parametros sniper correctos (min_conf=0.65, rsi=[32, 68])")

    print("\n=== TEST 2: CÁLCULO BANDAS DE BOLLINGER ===")
    closes = [Decimal(str(100 + (i % 3) * 0.5)) for i in range(30)]
    upper, mid, lower = strat._calc_bollinger_bands(closes, period=20, num_std=2.0)
    assert upper > mid > lower, f"Error en Bollinger: {upper} > {mid} > {lower}"
    print(f"Bollinger Bands: Lower={lower:.4f}, Mid={mid:.4f}, Upper={upper:.4f} [OK]")

    print("\n=== TEST 3: DETECCIÓN DE MECHAS DE RECHAZO (PINBAR / HAMMER) ===")
    # Hammer/Pinbar: open=1.0820, close=1.0822 (body=0.0002), low=1.0815 (lower_wick=0.0005 >= 1.8x body), high=1.0823
    pat_bull = strat._detect_candle_pattern(
        open_p=Decimal("1.0820"),
        high_p=Decimal("1.0823"),
        low_p=Decimal("1.0815"),
        close_p=Decimal("1.0822")
    )
    print(f"Patrón detectado para Pinbar Alcista: '{pat_bull}'")
    assert "Martillo" in pat_bull or "Pinbar Alcista" in pat_bull

    # Shooting Star/Pinbar: open=1.0822, close=1.0820 (body=0.0002), high=1.0828 (upper_wick=0.0006 >= 1.8x body), low=1.0819
    pat_bear = strat._detect_candle_pattern(
        open_p=Decimal("1.0822"),
        high_p=Decimal("1.0828"),
        low_p=Decimal("1.0819"),
        close_p=Decimal("1.0820")
    )
    print(f"Patrón detectado para Pinbar Bajista: '{pat_bear}'")
    assert "Estrella Fugaz" in pat_bear or "Pinbar Bajista" in pat_bear

    print("\n=== TEST 4: FILTRADO DE RUIDO (NO SEÑAL EN CONTEXTO DÉBIL) ===")
    # Generar velas planas/ruidosas sin confluencia
    noisy_candles = []
    base_p = 1.0800
    for i in range(50):
        o = base_p + (i % 2) * 0.0002
        c = base_p + ((i + 1) % 2) * 0.0002
        h = max(o, c) + 0.0001
        l = min(o, c) - 0.0001
        noisy_candles.append([i, o, h, l, c, 100])
    
    market_data_noisy = {"EURUSD-OTC": noisy_candles}
    signals_noisy = strat.generate_signals(market_data_noisy, {})
    print(f"Señales en mercado ruidoso (deben ser 0): {len(signals_noisy)}")
    assert len(signals_noisy) == 0, "Error: La estrategia no debe disparar con ruido sin confluencia"
    print(f"Pensamiento IA EURUSD-OTC: {strat.latest_thoughts.get('EURUSD-OTC')}")

    print("\n=== TEST 5: DISPARO DE SEÑAL SNIPER CALL CON TRIPLE CONFLUENCIA ===")
    # Construir escenario bajista previo que toca banda inferior, RSI extremo y genera pinbar alcista
    confluence_candles = []
    p = 1.1000
    for i in range(40):
        p -= 0.0008  # fuerte caída para llevar RSI abajo y romper banda inferior
        confluence_candles.append([i, p + 0.0003, p + 0.0004, p - 0.0001, p, 100])
    
    # Vela final: Pinbar de rechazo alcista en el piso atravesando la banda inferior
    last_open = p
    last_low = p - 0.0040  # mecha larga inferior que perfora la banda de Bollinger
    last_close = p + 0.0003  # cuerpo pequeño verde
    last_high = last_close + 0.0001
    confluence_candles.append([40, last_open, last_high, last_low, last_close, 200])

    market_data_call = {"EURUSD-OTC": confluence_candles}
    signals_call = strat.generate_signals(market_data_call, {})
    print(f"Pensamiento IA Test 5: {strat.latest_thoughts.get('EURUSD-OTC')}")
    print(f"Señales generadas con triple confluencia: {len(signals_call)}")
    assert len(signals_call) == 1, "Debería generar 1 señal CALL de alta precisión"
    sig = signals_call[0]
    print(f"Señal: {sig.symbol} {sig.signal_type.value} | Conf={sig.confidence:.2f} | Razón: {sig.reason}")
    assert sig.confidence >= Decimal("0.65"), f"Confianza insuficiente: {sig.confidence}"
    assert sig.metadata.get("direction") == "CALL"

    print("\n=== TEST 6: DISPARO DE SEÑAL SNIPER PUT CON TRIPLE CONFLUENCIA ===")
    put_candles = []
    p_up = 1.0500
    for i in range(40):
        p_up += 0.0008  # fuerte subida para llevar RSI arriba
        put_candles.append([i, p_up - 0.0003, p_up + 0.0001, p_up - 0.0004, p_up, 100])
    
    # Vela final: Pinbar de rechazo bajista (Estrella Fugaz) perforando banda superior
    put_open = p_up
    put_high = p_up + 0.0040  # mecha larga superior
    put_close = p_up - 0.0003  # cuerpo pequeño rojo
    put_low = put_close - 0.0001
    put_candles.append([40, put_open, put_high, put_low, put_close, 200])

    market_data_put = {"GBPUSD-OTC": put_candles}
    signals_put = strat.generate_signals(market_data_put, {})
    print(f"Pensamiento IA Test 6: {strat.latest_thoughts.get('GBPUSD-OTC')}")
    print(f"Señales generadas con triple confluencia PUT: {len(signals_put)}")
    assert len(signals_put) == 1, "Debería generar 1 señal PUT de alta precisión"
    sig_put = signals_put[0]
    print(f"Señal: {sig_put.symbol} {sig_put.signal_type.value} | Conf={sig_put.confidence:.2f} | Razón: {sig_put.reason}")
    assert sig_put.confidence >= Decimal("0.65"), f"Confianza insuficiente: {sig_put.confidence}"
    assert sig_put.metadata.get("direction") == "PUT"

    print("\n=== TODOS LOS TESTS PASARON EXITOSAMENTE (100% OK) ===")

if __name__ == "__main__":
    test_sniper_strategy()
