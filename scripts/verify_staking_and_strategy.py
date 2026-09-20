import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from decimal import Decimal
from app.engine.staking_manager import StakingManager
from app.engine.session_manager import SessionManager
from app.strategies.ai_learning_strategy import AILearningStrategy

def test_staking():
    print("=== TEST 1: STAKING MANAGER ($50 -> $100 -> $200) ===")
    sm = StakingManager()
    assert sm.get_current_stake() == Decimal("50.0"), f"Expected $50, got {sm.get_current_stake()}"
    print("✓ Paso 1 inicial:", sm.get_current_stake(), "USD")

    # Pérdida 1 -> Debe pasar a $100
    res1 = sm.record_trade_result(is_win=False, profit_usd=-50.0, symbol="EURUSD-OTC")
    assert sm.get_current_stake() == Decimal("100.0"), f"Expected $100, got {sm.get_current_stake()}"
    print("✓ Tras pérdida 1, Siguiente postura:", sm.get_current_stake(), "USD (Paso 2)")

    # Pérdida 2 -> Debe pasar a $200
    res2 = sm.record_trade_result(is_win=False, profit_usd=-100.0, symbol="EURUSD-OTC")
    assert sm.get_current_stake() == Decimal("200.0"), f"Expected $200, got {sm.get_current_stake()}"
    print("✓ Tras pérdida 2, Siguiente postura:", sm.get_current_stake(), "USD (Paso 3 Hard Cap)")

    # Pérdida 3 -> Freno de seguridad! No debe pasar a más, debe reiniciar a $50
    res3 = sm.record_trade_result(is_win=False, profit_usd=-200.0, symbol="EURUSD-OTC")
    assert sm.get_current_stake() == Decimal("50.0"), f"Expected reset to $50, got {sm.get_current_stake()}"
    assert res3["event"] == "LOSS_RESET_PROTECTION", f"Expected LOSS_RESET_PROTECTION, got {res3['event']}"
    print("✓ Tras pérdida 3, Freno activado y reinicio seguro:", sm.get_current_stake(), "USD (Paso 1)")

    # Ahora probamos ganar en Paso 2
    sm.record_trade_result(is_win=False, profit_usd=-50.0, symbol="EURUSD-OTC")
    assert sm.get_current_stake() == Decimal("100.0")
    sm.record_trade_result(is_win=True, profit_usd=87.0, symbol="EURUSD-OTC")
    assert sm.get_current_stake() == Decimal("50.0"), f"Expected reset to $50 after win, got {sm.get_current_stake()}"
    print("✓ Tras ganar en Paso 2, reinicio inmediato a base:", sm.get_current_stake(), "USD")

def test_session():
    print("\n=== TEST 2: SESSION MANAGER (META 3.5% y MARATON 10K) ===")
    sess = SessionManager(target_mode="3.5%")
    assert sess.get_target_pct() == Decimal("3.5"), f"Expected 3.5%, got {sess.get_target_pct()}"
    sess.sync_starting_equity(Decimal("5400.00"))
    
    prog = sess.get_progress_data()
    print(f"✓ Saldo inicial: ${prog['starting_equity']:.2f} USD | Meta: +{prog['target_pct']}% (${prog['target_amount']:.2f} USD)")
    assert prog["target_amount"] == Decimal("189.00")

    # Trade 1: +$43
    r1 = sess.record_trade_result(net_profit=Decimal("43.50"), is_win=True, current_equity=Decimal("5443.50"))
    assert not r1["is_target_reached"]

    # Trade 2: +$43
    r2 = sess.record_trade_result(net_profit=Decimal("43.50"), is_win=True, current_equity=Decimal("5487.00"))
    assert not r2["is_target_reached"]

    # Trade 3: +$43
    r3 = sess.record_trade_result(net_profit=Decimal("43.50"), is_win=True, current_equity=Decimal("5530.50"))
    assert not r3["is_target_reached"]

    # Test Marathon 10K
    marathon = SessionManager(target_mode="MARATON_10K")
    marathon.sync_starting_equity(Decimal("3143.00"))
    m_res = marathon.record_trade_result(net_profit=Decimal("176.00"), is_win=True, current_equity=Decimal("3319.00"))
    assert not m_res["is_target_reached"], "Marathon should NOT stop at 3319 USD"
    m_win = marathon.record_trade_result(net_profit=Decimal("7000.00"), is_win=True, current_equity=Decimal("10319.00"))
    assert m_win["is_target_reached"] and m_win["target_reason"] == "META_10K_ALCANZADA", "Marathon must reach target on >10k"
    print("✓ Modo Maratón 10K verificado: Solo frena al superar $10,000 USD.")


    # Trade 4: +$43
    r4 = sess.record_trade_result(net_profit=Decimal("43.50"), is_win=True, current_equity=Decimal("5574.00"))
    assert not r4["is_target_reached"]

    # Trade 5: +$43 (Total acumulado: $217.50 > $189 -> META ALCANZADA!)
    r5 = sess.record_trade_result(net_profit=Decimal("43.50"), is_win=True, current_equity=Decimal("5617.50"))
    assert r5["is_target_reached"], "Target should be reached"
    assert r5["just_reached"], "Should flag just_reached"
    print(f"✓ Meta alcanzada con éxito! Ganancia sesión: +${r5['session_profit']:.2f} USD (+{r5['session_profit_pct']:.2f}%)")

def test_anti_countertrend():
    print("\n=== TEST 3: ESTRATEGIA ANTI-CONTRA-TENDENCIA ===")
    strat = AILearningStrategy(symbols=["EURUSD-OTC"])
    
    # Crear serie de velas en tendencia bajista fuerte (precio cae de 1.1000 a 1.0800)
    import time
    base_t = int(time.time()) - 3600
    candles_downtrend = []
    price = 1.1000
    for i in range(40):
        o = price
        c = price - 0.0005
        h = o + 0.0001
        l = c - 0.0001
        price = c
        candles_downtrend.append([base_t + (i*60), o, h, l, c, 100])
    
    signals = strat.generate_signals({"EURUSD-OTC": candles_downtrend}, {})
    # En tendencia bajista fuerte, no debe haber señal de CALL (comprar contra el tren)
    call_signals = [s for s in signals if s.side.value == "BUY"]
    assert len(call_signals) == 0, f"Error: Se generaron {len(call_signals)} señales CALL contra la tendencia bajista!"
    print("✓ Confirmado: Cero señales CALL generadas en tendencia bajista fuerte (Filtro Anti-Contra-Tendencia activo).")

if __name__ == "__main__":
    test_staking()
    test_session()
    test_anti_countertrend()
    print("\n🎉 ¡TODOS LOS TESTS PASARON A LA PERFECCIÓN!")
