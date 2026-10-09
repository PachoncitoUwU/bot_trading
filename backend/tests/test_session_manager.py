import pytest
from decimal import Decimal
from datetime import datetime, timedelta
import time
from app.engine.session_manager import SessionManager

def test_session_manager_init_and_sync():
    sm = SessionManager(
        target_mode="3.5%",
        hourly_cycle_enabled=True,
        rest_minutes=50,
        weekend_autopilot=True,
        weekend_deadline=datetime(2026, 10, 11, 23, 59, 59)
    )
    assert sm.weekend_autopilot is True
    assert sm.session_max_trades == 7
    assert sm.rest_minutes == 50
    assert sm.cycle_state == "ACTIVE"

    sm.sync_starting_equity(Decimal("9388.24"))
    assert sm.session_starting_equity == Decimal("9388.24")
    assert sm.weekend_start_equity == Decimal("9388.24")

def test_session_manager_7_trades_triggers_limit():
    sm = SessionManager(
        target_mode="3.5%",
        rest_minutes=50,
        weekend_autopilot=True
    )
    sm.sync_starting_equity(Decimal("10000.00"))

    for i in range(6):
        res = sm.record_trade_result(Decimal("10.00"), True, Decimal("10010.00"))
        assert res["is_target_reached"] is False

    # 7th trade triggers limit
    res7 = sm.record_trade_result(Decimal("-55.00"), False, Decimal("1000.00"))
    assert res7["is_target_reached"] is True
    assert res7["target_reason"] == "SESSION_LIMIT_7_REACHED"
    assert sm.total_weekend_trades == 7
    assert sm.total_weekend_wins == 6
    assert sm.total_weekend_losses == 1

def test_session_manager_section_rest_and_resume():
    sm = SessionManager(
        target_mode="3.5%",
        rest_minutes=1, # 1 minute for test
        weekend_autopilot=True
    )
    sm.sync_starting_equity(Decimal("1000.00"))
    sm.record_trade_result(Decimal("46.20"), True, Decimal("1046.20"))

    rest_info = sm.start_section_rest(rest_minutes=1, reason="SESSION_LIMIT_7_REACHED")
    assert sm.cycle_state == "RESTING"
    assert rest_info["section_number"] == 1
    assert rest_info["rest_minutes"] == 1

    # Can trade should be False while resting
    can_trade, msg, just_resumed = sm.check_cycle_status()
    assert can_trade is False
    assert just_resumed is False

    # Simulate rest completion
    sm.cycle_start_time = time.time() - 65 # 65 seconds passed
    can_trade_after, msg_after, just_resumed_after = sm.check_cycle_status()
    assert can_trade_after is True
    assert just_resumed_after is True
    assert sm.cycle_state == "ACTIVE"
    assert sm.session_closed_trades == 0  # reset for new section!

def test_session_manager_weekend_deadline():
    past_deadline = datetime.now() - timedelta(minutes=5)
    future_deadline = datetime.now() + timedelta(days=2)

    sm_past = SessionManager(weekend_deadline=past_deadline)
    assert sm_past.is_weekend_finished() is True

    sm_future = SessionManager(weekend_deadline=future_deadline)
    assert sm_future.is_weekend_finished() is False
