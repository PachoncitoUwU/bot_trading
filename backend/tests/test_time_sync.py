"""Unit Tests for Time Synchronization Manager."""
import time
from app.core.time_sync import TimeSyncManager


def test_time_sync_calculates_drift_correctly():
    manager = TimeSyncManager(max_allowed_drift_ms=500)
    local_now = int(time.time() * 1000)

    # Server is 200ms ahead
    server_time = local_now + 200
    is_healthy, drift = manager.sync_with_server_time(server_time)

    assert is_healthy is True
    assert 150 <= drift <= 250
    assert manager.is_synced is True


def test_time_sync_detects_unhealthy_drift():
    manager = TimeSyncManager(max_allowed_drift_ms=500)
    local_now = int(time.time() * 1000)

    # Server is 1500ms behind
    server_time = local_now - 1500
    is_healthy, drift = manager.sync_with_server_time(server_time)

    assert is_healthy is False
    assert drift <= -1400
